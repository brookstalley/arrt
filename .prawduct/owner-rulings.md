# Owner rulings

Dated rulings by the owner, recorded before work proceeds on them. Where an
artifact already carries a ruling inline, that artifact is the home and this
file points to it.

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
