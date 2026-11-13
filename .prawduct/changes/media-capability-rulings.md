---
schema: 1
type: governance
scope: media-capability-rulings
date: 2026-11-13
title: The owner's rulings on heartbeat minor 5, and how a clip fits the frame limit
---
Settled before `contract-v1.1.0` is tagged, because a released tag is never moved.

- **The owner's rulings**, in the new `.prawduct/owner-rulings.md`: the four decisions
  `build-plan-player-media-capability.md` marked as inferred are confirmed (the frame
  limit is in, no clip duration yet, no `media` reads as still images, an unknown kind
  is ignored).
- **How a clip fits `video_max_frame`:** long side within the limit's long side, short
  side within its short side. The limit measures what a Player plays smoothly, not
  which way its screen is hung; whether a portrait or landscape clip belongs on a wall
  is the wall's shape range. Stated in `player-contract.md` § The heartbeat, minor 5
  and in the heartbeat schema's description, which ships in `arrt-contract` 1.1.0.
- **`.gitignore`** gains `.prawduct/.native-reviews/` and `.prawduct/.pr-body.md`, the
  two session entries prawduct's advisory named.
