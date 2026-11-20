---
schema: 1
type: fix
scope: audit-wave-2
date: 2026-11-19
title: The audit's second wave, first part: the server is checked where it is assembled, its records say what is true, and a catalogue an old release left can be read again
closes: [brookstalley/arrt#382]
---
This is the first of two parts of the audit's second wave (`build-plan-audit-wave-2.md`,
chunks 01 to 22). It changes what is checked and where code lives far more than what a
person sees: the records, the contract's next minor, CI that survives a pool outage, tests
of what ships, a type checker, the browser suite's retrying assertions and the split of
`DisplayService`. It closes one issue, #382. #441 and #442 (two flaky browser tests) are
touched and stay open: both tests now print what the page said when they fail, but the
cause of neither is established. #109, #110 and #150 (the drift probes) stay open too:
their red is now marked known-blocked, which silences nothing about the cause. #216 (the
store split) and #307 (three answers computed at many sites) are not closed. The part of
the wave that changes behaviour, the MCP surface's one break included, is the next plan's.

### Taken out of the wave, and why

- **The Library/Programming store split.** The owner ruled on 2026-11-19 that it is not a
  requirement now (`.prawduct/owner-rulings.md`, item 9). Nothing in this part builds
  toward it; the import guard, the foreign-key count and the events after commit that
  wave 1 left are kept as they are. #216 stays open with no wave.
- **WAL for the catalogue.** Not adopted (item 10, the builder's judgement): the store
  holds one serialised connection, so there is little for WAL to give, and it would add a
  `-wal` and `-shm` beside the file for a restore to miss. The backup now logs how long its
  copy took (`copy_seconds`), which is the figure that reopens it.
- **Arrt Player's contract pin.** Two of the Player's own chunks (the pin, and sending
  `settings_url`) moved to its next plan, because the tag they pin does not exist yet.

### What each chunk settled

**Records (01, 02).** The architecture describes what runs: one container on the NAS,
Players pulling over HTTP with a per-client token, no file channel; the single-Pi design is
in the Decision Log as history. The re-architecture's closed waves moved to an archive and
its status headers are true. The seam's rule 3 says it has no wave. *Theme* is the word
where a person reads, *the Library* and *Artworks* the others; "copy for the walls" and
Select on the right are recorded as the owner's rulings. The data model says what the
catalogue holds per device (the screen facts placement needs) beside the norm, which it
does not reword. The history's addresses and hostname are recorded as accepted residue, the
private readers' methods are out of the public artifacts' current text, and the old backlog
is archived.

**The contract, 1.2.0 (03).** Additive only; nothing a Player reads, writes or requests
has to change. New: `transport.json` (what each route answers, the `ETag` and `304` rule
with a conditional-GET vector replayed against the real server, the size bound of each
document, what no answer means); `vocabulary.json` (the words for each display state and
the two pairing fields); an optional `settings_url` in the client heartbeat (two valid and
five invalid fixtures; a server that gets one it refuses keeps the report and shows no
link); `defaults.bottom_weight` in the mat vectors; a fixture of a Player with several
labels and no walls, and one of a media URL on another host with its must-refuse twin; the
heartbeat's four singular fields described as superseded, still required; and frozen copies
of the 1.0.0 and 1.1.0 releases, which HEAD must still accept (`contract/released/`). The
package's source checks clean under `mypy --strict`. `manifest.v2`'s title and description
no longer call it a draft. **What the Player does about it: nothing yet.** It still pins
1.0.0, and a real Player at the commit `arrt/tests/system/player-ref.txt` names was run
against this server (chunk 08) and the pair disagreed about nothing. When it moves its pin
it may answer its double from `transport()`, send `settings_url`, quote `vocabulary()` and
read the bottom weight; it must add one reason for `media-url-empty.json` if it keeps a
table of reasons for refusing a fixture, which its parser already refuses. Done differently
from the plan: the server's mat judgement *quotes* the bottom weight, with a test that fails
if the two differ, because the image installs without the contract package.

**CI (04, 05).** When the pool cannot answer for ten minutes, `tests.yml` runs lint and the
governance, curation and contract suites on GitHub's runner, never the browser suite, and
its summary opens with one line saying where it ran; a red result is never retried or
rerouted, and a refused key or a bad wheel ends "Nothing ran". The job is named *Lint, then
every suite*, the check to require on `develop` and `main`. A drift probe red for a cause
nobody has established can be listed in `.github/known-blocked.json` with its issue and an
expiry within sixty days: a listed red is excused and named, an unlisted red, a listed green,
an expired row and a probe that never ran each fail by name. Six rows are listed (the Art
Institute's and dezoomify-rs's probes, #109 and #110), expiring 2027-01-18. The OpenRouter
probes (#150) are not: they are skipped for want of a key, and that is "never ran".

**The catalogue's life (06).** A migration chain from real old files: the dumps of
v0.1.0, v0.2.0, v0.3.0, v0.5.0, v0.7.0 and v0.10.0 are made by each release's own code and
opened by today's. It found a real defect, now fixed: a catalogue last opened by v0.1.0
could not be read, because its `tv_display` rendition rows survived the canvas migration and
reading one raised. The restore is a test too, and the old runbook was wrong in a way that
silently undid a restore (below). The catalogue records which release last opened it, when,
and whether its migrations finished (`catalogue_opened`), and a release meeting a file a
newer release opened refuses to start before it copies or changes anything.

**A misbehaving plugin (07).** A real plugin distribution, found by the loader's own
entry-point scan, is driven through a real Get: it raises; answers the wrong type, an
oversized or a malformed answer; finds nothing; hangs past its deadline and answers late (the
answer is discarded and in no later run); is called a fifth time while four still run (the
call is not made); declares a deadline past the ceiling (refused at load); uses all of the
deadline it declared (heard); or has a reader that raises. Each ends as the plugin host
promises, with the server answering throughout.

**A real Player against a real server (08).** `arrt/tests/system/test_a_real_player.py`
runs `python -m arrt` and a real Arrt Player as two processes and compares both sides: the
client document `200` then `304`, both works' media fetched by hash, the feed, the
heartbeats, what `/api/walls` says against what the Player drew, a label drawn, and every
route refusing after the token is replaced while the wall keeps showing. Marker
`player_e2e`, off by default; the commands are in `docs/testing.md`. The Player is pinned to
a commit of its integration branch, not a tag (none carries the file outputs yet). The
`player` job in `image.yml` that runs it against the built image has never run.

**The type checker (09, 10, 11).** `uv run mypy` runs in `arrt/` and `contract/` in CI's lint
step. The seam between the Library and Programming is checked strictly, and
`services/conformance.py` states in types that the SQLite adapters satisfy the seam's
Protocols. The tree began with 110 errors in 33 modules; the list of modules excused from
the check is empty, with no new `cast`, `Any` or `type: ignore`. `tests/preferences/test_type_gate.py`
holds the shape. None of the audit's three real signature confusions misbehaved at run time.

**The browser suite (12 to 19).** A one-shot read asserts on whichever side of a repaint it
fell, which was most of the suite's flakes. The suite now reads the page through Playwright's
retrying `expect`, `expect` waits as long as a locator does, and a guard
(`arrt/tests/unit/test_browser_reads_retry.py`) refuses a new one-shot read or fixed sleep
unless its line says why. `docs/testing.md` holds the table of forms and the hazards, each measured
on Playwright 1.62 or marked as reported. The conversion found tests that passed by
timing: a declined dialog's "No keeps it" stayed green when Cancel removed the thing,
because the server's state was read before the client's request went out. #442 reproduced once
in 240 runs under load and #441 not in 180, and the cause of neither is established; each
test now asserts so the next red prints what the page held.

**`DisplayService` (20, 21).** It is a facade of one-line delegations over `feeds.py`,
`themes.py`, `walls.py`, `scenes.py` and `reports.py`, each calling only the publisher and
the modules before it; every surface still calls `services.display.<method>`. The moves were
checked function by function against the originals (no function changed beyond a dropped
leading underscore and its prefix). The feed guard that checks every published feed against
the contract was re-pointed to where the builder now lives and shown to fire. This closes
#382 (scenes in `scenes.py`).

**Integration (22).** The records say what 2a built: `CLAUDE.md`'s dev commands, the plan's
dated notes, the norm index, the operator-verification entries for the restore, the real
Player and the CI fallback, and this record.

### Found, and left for the next part

- A feed a server *process* publishes is not checked against the contract: the guard
  patches only inside the test's own process.
- `DisplayService`'s moved methods still check before they write, outside the transaction
  that writes, in several places (`delete_theme`, `exclude_work`, `allow_work`,
  `remove_from_theme`, `make_default`, `update_theme`, `scene_walls`); and
  `scene_walls` reads with no read transaction, so a wall deleted at that moment ends as a
  `500`.
- The wall heartbeat answers `422` in FastAPI's own body, not the contract's error shape,
  for a body that is not a JSON object; `transport.json` states it as it is.
- A reader's fault reads on the work as an ordinary fetch failure and counts against it; a
  finished Get with a pending work carries no reason.

## Consumer note
Read the restore step first. **The corrected restore:** stop the server; remove
`catalogue.sqlite-journal` (and a `-wal` or `-shm`, if any) from beside the catalogue,
because a backup copied in beside a dead server's hot journal opens as that server's last
commit and the restore is silently undone; copy the newest `catalogue-*Z.sqlite` in beside
the catalogue and rename it over `catalogue.sqlite`; on a new machine restore `raw/`,
`presentation/` and `thumbs/`; start the server. There is no "hang each theme again" step.
Your own restore notes, if you keep them outside this repository, need the journal step.

**The first start adds one table, `catalogue_opened`, to the catalogue**, recording which
release opened it; nothing is dropped, so no copy is taken for it (a file that still needs a
migration that drops data is copied first to `pre-migration-<UTC instant>.sqlite`, as in
the previous release, and the server does not start if the copy cannot be written). From
then on a release that carries the record refuses to start on a file a newer release opened,
naming both. **The way back is still the copy taken before the migration and the previous
image together:** v0.11.0 does not carry the record and opens the file without a word, so
the refusal protects only a downgrade to a release that does. `backup.completed` in the
journal gains `copy_seconds`.

The MCP surface is unchanged in this part; its one allowed break is in the next. **Nothing
here needs a Player upgrade**: the contract's 1.2.0 is additive and the `contract-v1.2.0`
tag is cut after this merges, and Arrt Player may move its pin when it chooses. When the
pull request into `main` runs, the `player` job in `image.yml` runs for the first time; see
`.prawduct/operator-verification.md`.
