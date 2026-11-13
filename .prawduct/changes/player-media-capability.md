---
schema: 1
type: feature
scope: player-media-capability
date: 2026-11-11
title: A Player reports it plays animated and video media (#424)
---
Heartbeat minor 5 adds `capabilities.media`: the kinds of media a display shows
(`image`, `animated`, `video`) and, optionally, the largest video frame it plays
with no dropped frames. Arrt Player is gaining an mpv renderer that plays moving
media, and it sends the capability once a contract tag carries the field.

- **The schema** (`contract/schemas/heartbeat.v1.schema.json`) requires `kinds`
  and allows `video_max_frame` only beside `video`. Two valid fixtures (a Player
  that plays video up to 720p, and one that shows still images only) and three
  invalid ones (an unknown kind, no kinds, a frame limit without video), each
  invalid fixture failing on its named rule alone.
- **The prose** is `player-contract.md` § The heartbeat, minor 5: capabilities
  without `media` read as `kinds: ["image"]`, and a reader ignores a kind it does
  not know.
  A clip fits `video_max_frame` long side to long side and short side to short
  side; whether a portrait or landscape clip belongs on a wall is the wall's shape
  range (the owner, 2026-11-13).
- **The server is unchanged.** It keeps the heartbeat as it came, and its suite
  posts every valid heartbeat fixture to the real route, so it accepts minor 5.
- **`arrt-contract` 1.1.0**, a package minor.

**Not in this change:** moving media in a feed. Major 2's `media.content_type`
admits only JPEG and PNG and the Library holds no clips, so a clip's duration and
the owner's dwell rule wait for that change; #424 stays open for it.

## Consumer note

Arrt Player: pin `contract-v1.1.0` and send `capabilities.media` with
`schema.minor` 5. A server on 1.0.0 accepts it, because it does not check the
key, so the Player may upgrade first.
