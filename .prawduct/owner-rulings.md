# Owner rulings

Dated rulings by the owner, recorded before work proceeds on them. Where an
artifact already carries a ruling inline, that artifact is the home and this
file points to it.

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
