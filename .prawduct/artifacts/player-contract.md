---
artifact: player-contract
version: 1
depends_on:
  - artifact: re-architecture
  - artifact: api-contract
  - artifact: data-model
  - artifact: security-model
last_validated: null
status: major 1 describes the running system plus wave 2's additive changes; major 2 is a draft
---

# The Player Contract

**What Curatarr publishes for a wall, what Displayarr reports back, and how both
travel.** This file is the contract's home. `api-contract.md` § The Server↔Player
surface points here. `re-architecture.md` § Seam 2 is where the decisions behind
it were made.

The contract is three things, and they are kept together because each is only
half an answer alone:

- **Schemas** in `contract/schemas/`, JSON Schema Draft 2020-12, one per document
  and major. A schema states the **writer's obligations**: what a conforming
  document contains.
- **Fixtures** in `contract/fixtures/`, example documents, valid and invalid.
  `contract/fixtures/index.json` lists every one with the schema it is judged by.
  For an invalid manifest, the index also says whether a Player must refuse it.
- **This file**, for what a schema cannot carry. That covers when a reader
  refuses, what it keeps when it does, what a time means, and which wave brings
  what.

**Who tests what.** The root suite (`tests/preferences/test_player_contract.py`)
checks that the fixtures and schemas agree. Every invalid fixture must break
exactly one rule, the one its filename names. Curatarr's suite validates
manifests its real builder writes, and runs its heartbeat reader over the
heartbeat fixtures. Displayarr's suite runs its manifest reader over the manifest
fixtures and validates the heartbeat it writes. When Displayarr moves to its own
repository (wave 5), it pins a copy of `contract/` and runs the same tests
against it. Curatarr owns the contract, and a Player that needs a field asks
for it here.

## Versioning

Both documents carry `schema: {major, minor}`. The manifest has always carried
it. The heartbeat gains it in wave 2, and a heartbeat without one is 1.0.

- **A new major is a breaking change**: a field removed, a meaning changed, a new
  required key. A reader refuses a major it does not know and **keeps what it
  already has**. For the Player that means the last good manifest, so the wall
  goes on showing yesterday's theme rather than a misreading of today's.
- **A new minor is additive** and free. A reader ignores a minor it does not know,
  and ignores keys it does not recognise.
- **The schemas allow unknown keys** for that reason, and `unknown-minor-and-key`
  is a valid fixture.
- **A reader may be more tolerant than a schema.** The schema says what a writer
  must produce. A Player refuses only what the index marks `player_must_refuse`,
  which is what it cannot act on safely, and it tolerates the rest. The manifest
  fixtures `absolute-render-path`, `media-sha256-not-hex` and
  `generated-at-without-offset` break writer obligations that today's reader
  does not police.

**Every instant is RFC 3339 with an offset.** Each schema backs its `date-time`
with an explicit pattern, because a JSON Schema validator does not have to check
`format`, and the common Python one does not unless an optional package is
installed. A timestamp without an offset would then pass silently.

## Major 1

### The manifest

`contract/schemas/manifest.v1.schema.json`. Minor 1 is what the curation plane's
`manifest/builder.py` writes today. Minor 2 (wave 2) adds `media` to each entry.

- **The wall is named by where the document lives**, never inside it: today by
  the file name `theme-manifest-{wall_id}.json`, from wave 2 by the URL
  `/walls/{wall_id}/manifest`. A Player configured for one wall cannot read
  another's by mistake.
- **A wall with nothing hanging has no manifest.** The builder refuses to build
  one. A wall whose theme holds nothing ready has a manifest with an empty
  `entries` list, which is an ordinary state.
- **Membership is readiness.** Every entry can be rendered, and works that
  cannot are reported to the curator, never sent to the Player.
- **`directive.sequence` and `pinned_work_id`** carry `show_now` and `next`. Their
  semantics (when a sequence counts as consumed, what an unresolvable pin does,
  and why a pin issued while the set is asleep waits) live in `data-model.md`
  § Directive and `api-contract.md` § How `art_display` reaches the display plane.
  They are not restated here.
- **`render_path` stays required for all of major 1.** From wave 3 no Player
  reads it, because the file channel is retired, but removing a required field
  is breaking, so it goes with major 2.
- **`label` carries text only.** The artist's name crosses whole and in parts,
  because a work whose artist has no recorded parts has only the whole. Every
  label key is present, with `null` for a fact the catalogue lacks.

### The heartbeat

`contract/schemas/heartbeat.v1.schema.json`. It holds facts, not a verdict: no
"healthy", no threshold. The reader decides what the facts mean.

- **`reported_at` is the one key the server depends on.** Curatarr treats a
  heartbeat without it as unreadable, which reports the Player as broken. The
  spelling is fixed for that reason, and `tests/preferences/test_heartbeat_contract.py`
  checks both planes spell it the same.
- **`has_label_surface` is never null.** It separates a Player with no panel from
  a Player whose panel has not drawn yet, a distinction `null` used to blur.
- **Written every 60 seconds.** On the file channel that is an SD-card wear
  budget. Over HTTP it stays, because it sits under the shortest rotation
  interval with margin.
- **Minor 1 (wave 2)** adds the `schema` key.

### Transport (wave 2)

The file channel keeps working until wave 3 retires it. Over HTTP:

| Route | Body | Answers |
|---|---|---|
| `GET /walls/{wall_id}/manifest` | none | `200` with the manifest and an `ETag`; `304` when `If-None-Match` matches. Polled about once a second |
| `GET /media/sha256-{hex}` | none | `200` with the image, `Cache-Control: public, max-age=31536000, immutable`. A hash never serves different bytes |
| `POST /walls/{wall_id}/heartbeat` | the heartbeat | `204` |

- **Every request carries the wall's token** as `Authorization: Bearer <token>`.
  Curatarr issues one per wall from its UI, shows it once and keeps only a
  verifier. A missing or wrong token is `401`, and a token for another wall is
  `403`. `/media/...` accepts any wall's valid token.
- **Media is addressed by the SHA-256 of its bytes.** The manifest gives `url`,
  `sha256`, `bytes` and `content_type`. The Player verifies the hash after
  download and discards a mismatch, so a corrupted transfer is never shown.
- **Every failure keeps the cache.** Transport errors, timeouts and `5xx` mean
  the server is unreachable: the Player backs off and keeps showing what it
  has. `401`, `403` and a `404` on the wall are configuration errors, stated
  once in the journal. A `404` on a media hash skips that work and keeps
  rotating. An unknown major is refused and the last good manifest is kept. The
  wall going black is always worse than the wall being incomplete.
- **In waves 2 and 3, `/media/...` serves the composed render** that
  `render_path` names. From wave 4 it serves the presentation master.

## Major 2 (draft)

Written in Chunk 02 of `build-plan-wave-1-contract.md`.
