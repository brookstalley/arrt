# Owner rulings

Dated rulings by the owner, recorded before work proceeds on them. Where an
artifact already carries a ruling inline, that artifact is the home and this
file points to it.

## 2026-11-25: how Arrt tells Hearsay (#451)

Three recommendations put to the owner while #451's requirements were written, after
Hearsay's session had answered the intake questions (size, Wikidata, readers, the
Art Institute's search). The owner: "yes to all recommendations". As ruled:

1. **One copy point, in the host, and a label per plugin.** The code that loads and
   calls source plugins hands each one an HTTP layer that copies the text documents
   it reads into a queue on disk, and records each search where the host calls the
   plugin. Each plugin declares which of its requests are records and which carry
   Arrt's own query; an unlabelled request is never told. Chosen over a tell written
   into each plugin's fetch code, so a new in-tree plugin is covered by the same
   mechanism. Cost accepted: a third-party plugin that does not use the host's HTTP
   layer is not told.
2. **The queue fills before anything is sent.** Sending stays off until the owner has
   looked at what is queued and turned it on. This is how "the first send takes the
   owner's approval" is met.
3. **No backfill in the first plan.** Arrt kept no museum documents, so Hearsay
   starts with what Arrt fetches from now on. Refetching the Library's records for
   Hearsay is a backlog item of its own.

## 2026-11-25: Arrt contributes to Hearsay's knowledge graph

Asked what Arrt should contribute to Hearsay (the owner's attributed claim store),
the owner: "Yes museum records, as well as any learnings from the agentic discovery
path". As ruled:

1. **Museum records.** The museum documents Arrt fetches become a source Hearsay
   keeps, read into world claims by a mapping per museum that the owner approves.
2. **What discovery learns.** Phase 1's proposed works, phase 2's judgement that a
   museum record is or is not the requested work, and what each provider's search
   returned, told to Hearsay as Arrt's own attributed statements.

**Timing, the same day.** Hearsay's session proposed taking Arrt after its music
demo's current part ships. The owner declined: "we need to start contributing soon,
but the full stack may not accept or process our data until post-demo". So Arrt
starts telling Hearsay what it fetches and judges soon, and Hearsay may only keep it
(no mapping, no art vocabulary) until after the demo. The intake shape is still
Hearsay's to name, and anything leaving the machine still takes the owner's approval.

## 2026-11-20: six answers while part 2b was finishing

Six questions stood, each with the advisor's recommendation, at the end of every report
while part 2b (`build-plan-audit-wave-2b.md`) was being integrated. The owner: "Yes to all
recommendations, you can do the grant". As ruled:

1. **This project may use the pool's host executor, and the advisor may grant it.** Asked so
   that the server image's test stage can run on the pool, outside a container, at no cost
   in GitHub's minutes. Granted the same day: the pool's allowlist now gives this project
   the container and the host executors. What it permits is this repository's tests
   running image builds directly on a runner. Built in that plan as Chunk 65; until it
   lands, the image's test stage is still first met at a pull request into `main`.
2. **A wall may keep its first picture up to one interval longer when a neighbour is
   refused.** The schedule fix lines a republished wall up with the wall built just
   before it; when a same-pace neighbour is refused, the wall acted on is built against
   that neighbour's published schedule. Accepted as built.
3. **One scratch pull request, once, at the end of part 2b**, to see the reworked CI
   fallback run on GitHub's runner. It is closed unmerged. This is the one exception the
   same day's ruling on CI's minutes allows itself here.
4. **MCP keeps the new tool `art_spend`.** It adds one entry to every client's tool
   listing; the Spend history is not discovery, and `art_discovery`'s description was at
   the client's limit.
5. **The periodic reconcile of feeds may make an act wait, once per half hour, until its
   lookups are batched.** Measured in-process on one machine with nothing to fix: about
   0.4 s at 2,000 works and 1.1 to 2.5 s at 5,000, the store's lock held throughout,
   and longer on the deployment's slower machine. Batching the lookups is a third part's.
6. **The delegate-verification policy's count is corrected.** `project-preferences.md`
   `## Workflow`, `Delegate verification`, said a change to `contract/` "runs all four"
   suites; there are five since the real-Player suite. The norm's text now says five.
   This is a count brought up to date, and changes nothing else the policy says.

## 2026-11-20: an agent may post its measurements on the issue it is working

A build delegate working a flaky test (#442) posted what it had measured as a comment on
that issue, unasked. The advisor asked whether that is wanted, recommending "allowing it
for measurements on an issue the chunk is working, and nothing else". The owner: "Yes to
2". As ruled: an agent may comment on a GitHub issue when the issue is the one its own
work is settling and the comment is what it measured or established (what was run, what
was seen, what was ruled out). It opens, closes, labels and edits no issue on its own,
comments on no other issue, and writes nothing there that this public repository's rule
keeps out of a tracked file (no network address, hostname or username) and no attribution
line. Closing an issue stays the merge's act.

## 2026-11-20: a hang can be started from Walls; hanging for a duration waits

Asked while part 2b was being built (question 2 of the wave's decisions: hanging for a
duration, and a wall-side way to hang chosen works). The advisor recommended yes to starting
a hang from the Walls screen, "it's where you look when deciding what a wall shows", and
deferring durations "until you've used the rest". The owner: "Yes to your recommendations".
As ruled:

1. **Walls gains a way to hang chosen works on a wall.** A wall's *Hanging* picker, which
   today offers only themes, also offers choosing works: it opens Artworks selecting for
   that wall, and the selection's *Hang…* (built in `build-plan-audit-wave-2b.md`'s Chunk
   34) hangs them there. Built in this plan as Chunk 57.
2. **Hanging for a duration is not built now.** A hang still lasts until it is changed. It
   is a persisted format (what "before" is when two hangs overlap, what a delete does to
   it), so when it is built it is designed from its consumers' questions in a plan of its
   own. `user-scenarios.md`'s scenario of a day or two outside the household's taste stays
   unmet until then, and the records say so.

## 2026-11-20: CI is kept small, tests run on the pool first, and CI makes no paid call

Asked while part 2b was being built (which pool runners may run this repository, and what
ceiling the CI's model key should have). The owner: "All runners are fine. We should
minimize CI and prioritize local tests. We are almost out of ci minutes. The pool has six
runners, not one. Ci should not make paid calls". As ruled:

1. **Every runner of the pool may run this repository's tests.** The advisor's question
   assumed one runner; the pool has six.
2. **CI is kept small, and tests run from the machine doing the work come first.** A pull
   request's evidence is the pool run made before it is opened (`testament run`, `AGENTS.md`
   § Running tests); CI confirms that run, it is not where a change is first tested.
   GitHub's runner minutes are nearly spent, so nothing adds work to GitHub's runners, and
   work that runs there today is moved to the pool or to pull requests into `main` where it
   can be. This sharpens the 2026-11-18 ruling below (no heavy builds on GitHub's runners);
   it does not withdraw ruling 4 of 2026-11-19 (an outage must not block a merge): the
   fallback stays, and costs minutes only while the pool cannot answer.
3. **CI makes no paid call.** No workflow holds a model key or reaches a paid service;
   probes and evaluations that cost money are run by hand (`live_api`, `llm_eval`). That
   answers the standing question on the drift probes that need a key (#150): they are not
   CI's.

What it changes in `build-plan-audit-wave-2b.md`: the real-Player suite (Chunk 29) runs on
the pool and the fallback leaves it out by name; a chunk added the same day (56) takes the
image's test stage off GitHub's runner for ordinary pull requests.

## 2026-11-19: during wave 2 of the audit fixes, two rulings

Asked while part 2a's pull request (#446) was in its checks. The owner: "The testament
endpoints are public knowledge, not secrets. Other than that, yes to recommendations".

1. **The test pool's endpoints are public, not secrets.** The advisor had recommended
   turning the workflow's console and coordinator addresses from repository variables
   into secrets, because they print in the public Actions log of every run. Declined:
   they are public knowledge. They stay variables, and their appearing in a workflow log
   is not an exposure. This does not widen the repository's own rule: tracked files still
   carry no network address, hostname or username (`CLAUDE.md`, the hygiene guard).
2. **Arrt Player removes from a television only the pictures it recorded uploading**, in
   a later wave. Today it clears every uploaded picture it cannot account for on a set
   (`arrt-player`'s `security-model.md` § What it does to the television), so a Frame
   address that points at another television clears that set's uploads, the household's
   own included. Now that the Player's store records which set its bindings were made on,
   it can keep a record of its own uploads per set and leave everything else alone. Not
   built in wave 2, which ships the recorded behaviour unchanged; it goes in the next
   Arrt Player plan, with what replaces the orphan sweep's job of cleaning up after a
   failed upload. Recorded here because the question was asked in this repository's
   session; the Player's own rulings file takes a pointer when that plan is cut.

## 2026-11-19: after wave 1 of the audit fixes, ten rulings

Asked at the end of wave 1 (`build-plan-audit-wave-1.md`, merged as #445), each with
the advisor's recommendation. The owner: "Yes to all of your recommendations except
the root ownership in number 7", and a qualification on number 8. As ruled:

1. **Theme, not playlist, wherever a person reads.** The contract's `playlist`
   field keeps its name until the contract's next breaking version.
2. **The household's holdings are the Library; the screen is Artworks.** The other
   names (collection, catalogue) leave what a person reads.
3. **The MCP surface may break, once.** `work_id` becomes `artwork_id` in wall
   outputs and the acts on a wall are gathered into one tool, in one release,
   announced in the change record.
4. **CI is required to merge on `develop` and `main`, in all three repositories,
   once the pool has a fallback.** The fallback comes first: an outage of the pool
   must not block every merge.
5. **The API-drift alarm's blocked probes are marked known-blocked**, so a real
   drift shows again. They are not each investigated by hand.
6. **Five calls made in wave 1 are confirmed:** "copy for the walls" is the
   household's word for the presentation master; Select stands last on a list
   screen's toolbar, on the right; the `.local` name the Player's settings page and
   its tests use is an example, not a real host; a guesser with
   two addresses can hold a device that has never signed in out of a Player's
   settings page for as long as the guessing continues; a "database is locked"
   error pauses the acquisition queue and is not counted against the work.
7. **Not now: the Player's code owned by root with `ProtectSystem=strict`.**
   "That's just too heavy for right now. We may do that eventually, but not yet."
   mpv goes on running as the service account, able to read its settings; the
   sandboxing wave 1 added stands as it is.
8. **One label panel per Player is the recorded limit for now, and nothing may be
   designed that closes off several.** "I'm fine recording one label panel per
   player right now, but we shouldn't design anything that precludes having
   multiple labels, just as we don't prevent having multiple displays per player.
   In the future, there may be players that only do labels and might have multiple.
   We don't have to build that right now, but let's make sure we aren't closing off
   that path." So: a label is an output a Player has zero or more of, as a display
   is; a Player with labels and no display is a shape the contract, the server's
   records and the Player's configuration must be able to describe; what is built
   today may assume one.

9. **A Library/Programming split is not a requirement now.** Asked how media would
   be authorised after such a split (the contract promises a Player would not
   change; media is authorised by Programming's client tokens today), the owner:
   "Let's not worry about library and programming split. Right now, it's not a
   requirement." So the store split (`re-architecture.md` § Seam 1, rule 3; #216)
   has no wave and is not built toward; the seam rules already built and guarded
   (one-way imports through the facade, events after commit, reconciliation at
   start, the count of foreign keys crossing the seam) stand as they are, because
   they cost nothing to keep; and a sentence that promises what a split would or
   would not require of a Player describes a future nobody is building.
10. **WAL mode for the catalogue is the builder's judgement.** "For WAL, please use
    your judgment." The judgement, the coordinator's and not the owner's: stay on
    the rollback journal for now (`build-plan-audit-wave-2.md` records it and what
    would reopen it).

Earlier the same day, at the audit's close: the provider keys are temporary and
are not rotated ("don't sweat the keys"); the commits in public history that carry
private addresses are left alone for now ("leave commits alone, later we can get
that").

## 2026-11-18: CI runs on testament's pool, and no heavy builds on GitHub's runners

The owner, asked whether CI does too much: "please also check that we're not doing
too much in ci -- we should be using testament where possible and not doing heavy
builds. we keep running out of github actions minutes. I can get you a testament ci
token if we don't have one alread". They then created the CI key `arrt-ci-github`;
it is the `TESTAMENT_KEY` secret, and its coordinator the `TESTAMENT_COORDINATOR`
variable. This supersedes the 2026-10-06 ruling that sharded the browser suite
across four Actions jobs, and `build-plan-server-image.md`'s decision to build the
image on every pull request. Where it landed: `build-plan-ci-on-testament.md`.

## 2026-11-18: agentic patterns, four recommendations and a stopgap for #217

The advisor proposed four changes to how agents build here and a stopgap for the
stalled accessibility transition. The owner replied "yes to all recommendations":

1. Record the delegation policy in `project-preferences.md` § Workflow
   (`Delegation`, `Delegate verification`). It includes the two lessons of the
   #435/#374 cycle: plan deliverables are full repo-relative paths checked before
   dispatch, and a delegate returns proof that each new check fails on the unfixed
   code.
2. Turn the "a check that cannot fail" lesson into that required evidence, then
   compact `.claude/rules/learnings/core.md`, where it appears as several rules.
3. File the unfiled flaky browser tests and fix #432.
4. Move test-suite detail out of `CLAUDE.md` into `docs/testing.md`.
5. Record a stopgap, bounded at 60 days, on `accessibility-spec.md`'s
   in-transition norm, whose tracking item #217 has not moved since 2026-10-05.

Added by the owner the same day, mid-build: "for delegation please also capture
that subagents must never run heavy integration tests -- they run feature tests, and
the cooridnating agent or a dedicated integration subagent mainatin an integration
branch and are smart about testing proportionally". It is in `Delegate verification`.

Where each landed: `build-plan-agentic-patterns.md`.

## 2026-11-13: heartbeat minor 5, `capabilities.media` (#424, contract-v1.1.0)

The owner confirmed all four decisions
`archive/build-plan-player-media-capability.md` § Goals marked as inferred ("yes confirmed on all"):

1. The frame limit, `video_max_frame`, is in.
2. The manifest half is deferred: no `duration_s` in this minor.
3. Capabilities without `media` are read as `kinds: ["image"]`.
4. A reader ignores a kind name it does not know.

**How a clip compares to `video_max_frame`:** "We should assume walls are either
portrait or landscape, but NOT that a particular wall can rotate. So I think we
have to size based on a wall setting." The advisor's recommendation, a
rotation-tolerant comparison, was put to the owner again with its consequence
for a portrait wall stated, as two options: (A) the limit is reported as the
screen is hung and compared side by side, or (B) the limit is a decode limit,
compared long side to long side and short side to short side, and whether a
portrait or landscape clip belongs on a wall is the wall's shape range
(`data-model.md` § The wall's shapes). The owner chose **B** ("yeah B"), the
same day. `player-contract.md` § The heartbeat, minor 5 states it.

The owner approved pushing `contract-v1.1.0` once that sentence is merged, a
release, and its deploy to the NAS.
