# Owner rulings

Dated rulings by the owner, recorded before work proceeds on them. Where an
artifact already carries a ruling inline, that artifact is the home and this
file points to it.

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
