---
schema: 1
type: fix
scope: audit-wave-1
date: 2026-11-19
title: The audit's first wave: an agent's check no longer changes a wall, a hung plugin no longer stalls every Get, and a migration that drops data copies the catalogue first
closes: []
---
Eight reviewers audited the server on 2026-11-19. This is the first wave: every finding that
needed no ruling and depended on no other fix, in ten chunks (`build-plan-audit-wave-1.md`).
No issue is closed by it. #216 (the store split) and #313 (a durable record of each search)
are touched and stay open: a test now holds the one cross-seam foreign key at one, and a
plugin that only ever answers "could not be asked" now says so on Status, but neither the split
nor the record exists. The findings it leaves for the second wave, and the ones held for the
owner, are in the plan and its ledger.

## What an operator must know

- **A migration that drops data now copies the catalogue first, and refuses to proceed if it
  cannot.** Before any migration that drops a column or a table acts, the server copies the
  catalogue (`VACUUM INTO`, checked) to `pre-migration-<UTC instant>.sqlite`, in `BACKUP_DIR`
  or beside the catalogue when that is unset, and keeps the three newest outside the backup
  generations' count. If the copy cannot be written (a full disk, a read-only directory) the
  server **does not start**, naming the directory, and the catalogue is left as it was. A
  catalogue already on the current shape takes no copy. The manual `.backup` steps in
  `deploy/README.md` before earlier releases are still sound and are no longer needed.
- **Private source plugins must declare their deadlines before an image is built from this
  server.** Interface 1.5 gives every plugin call a deadline: 60 s for a finder and a reader,
  30 s for a preview and 120 s for a collection browse. A call past it is "could not be asked",
  and the work behind it waits. A plugin that reads through a browser takes longer than that,
  so it must declare `SourcePlugin(deadlines={"finder": …, "reader": …})` (keys `finder`,
  `reader`, `preview`, `browse`; seconds above zero and at most 3,600, or the plugin is refused
  at load). A 1.4 plugin loads unchanged on the defaults and would then answer "could not be
  asked" for every slow page. The private plugins' repository declares them from its measured
  bounds (1,012 s for one page, 2,044 s for Stedelijk's reader); until it has, build no image
  from this server with them.

## What else changed for someone running the server

- **MCP.** `art_display` gains `preview` (`wall_id`, `theme_id` optional), the read-only twin of
  `GET /api/manifest`: what a theme would put on a wall, nothing written. `sync` takes
  `wall_id` alone and refuses a `theme_id` by name; it used to publish a theme no wall was
  recorded as hanging. Tool descriptions that still said "no television writes" or
  "not this one again" are rewritten from the code.
- **The plugin host.** A call that outlives its deadline runs on a daemon thread, its late
  answer discarded and logged (`source.plugin_late`), at most four per plugin; past that a
  plugin is answered "could not be asked" without a call. One Get no longer sends the same
  Wikidata question once per plugin (a work's pages are remembered for ten minutes and
  concurrent asks share one request). Answers are checked beyond their type: a size that is not
  a positive whole number, text over 2,000 characters or a preview over `preview_max_bytes` is a
  fault. Two plugins claiming one URL are logged once per pair. Status says when a plugin has
  answered nothing but "could not be asked".
- **Consistency.** A wall or client act reads and writes inside one transaction, so a Player's
  heartbeat can no longer lose to an edit made at the same moment (a forced interleaving
  failed with a foreign-key error and lost a newly issued token on the old code). A hang's
  feed is staged and written as the last step of its transaction, so a later step that fails
  leaves the published feed as it was; the one window left, a crash between the renames and
  the commit, is healed at the next start. Archiving fifty works rebuilds each wall's feed once.
  A Frame moving between Players is logged at WARNING, naming both.
- **Files.** One atomic writer (unique staging name, synced before and after the rename) for
  masters, fetched images, pictures, thumbnails and the backup receipt, in place of several
  that staged at one fixed name. **`dezoomify-rs` is handed a new staging name**,
  `.<stem>.<token>.partial<suffix>`; the live `live_binary` test has not been run against it.
- **Backups survive a crash loop.** The start-up backup is skipped while the newest generation
  is younger than `BACKUP_INTERVAL_SECONDS`, so a server restarting every few minutes after an
  upgrade no longer replaces the generations from before it within the hour.
- **The Library.** Accepting a candidate promotes no scan the curator turned down. A Watch whose
  start was not recorded is not started again at once. A mat's spend is recorded before its
  colour. A full or read-only disk, or a database error, in the middle of a fetch pauses the
  queue (15 minutes) instead of counting against each work, which gave every work up in about
  four days. One work is prepared by one caller at a time.
- **The browser.** Setting up a wall no longer dead-ends: *Show it there* is disabled with its
  reason until the Player has reported a screen, and enables itself when it does; the token
  dialog has *Copy* and names the Player's own fields (*Token*, *Server address*); the Edit wall
  dialog has one filled act. Posters carry each work's title and artist; *Hang…* shows
  disabled, with its reason, on a work with no picture; every list page has its toolbar in one
  order, *Select* last on the right; back links are links. Ask with no key is disabled with one
  sentence; the budget line in the sidebar is a link to History filtered to Gets; the Queue has
  no per-row *Retry* and asks before retrying more than five. Walls, Players and Status no
  longer say "plane", "heartbeat" or "display" for a Player, and the sentences Topics, a failed
  match and a work with no source send name no setting or id; Settings › Sources and Status
  still name the setting, as the operator's pages.
- **Edges.** A Player's successful requests (`2xx`, `304`) write no access line (one wall wrote
  about 170,000 a day); refusals still do. A request to `/api` or `/mcp` the browser marks
  `Sec-Fetch-Site: cross-site` is refused (`403`); an MCP client, `curl` and a Player send no
  such header and are unaffected. Every HTML response carries `frame-ancestors 'none'` and
  `X-Frame-Options: DENY`, so a reverse proxy that serves the interface inside another page must
  say otherwise. A Player route's body over 256 KiB is refused with `413`. The example compose
  file publishes the port to one address, never every interface (**check your real file**), and
  bounds Docker's log.
- **`deploy/curation.service` is deleted**, with the five tests that guarded only it. Nothing
  had run it since the server moved to the NAS.
- **The synthetic UX walk** (`arrt/tools/ux_walk.py`) boots its server from an allowlisted
  environment with every `.env.example` name blank, so it can no longer read a key from the
  operator's `.env` and spend.
- **CI and guards.** Every action in `.github/workflows/` is pinned by commit SHA (a test fails
  on one that is not); `issues: write` is off the job that holds the OpenRouter key;
  `image.yml` builds the image's test target unfiltered on every pull request into `main`; the
  seam guard counts the Library's five storage modules as the Library's; a new test holds the
  catalogue file's cross-seam foreign keys at exactly one; the deployment-values scan reads
  every tracked text file and knows tailnet, IPv6 local, `.lan`/`.local` and account-at-machine login shapes.
  The pins and the new `image.yml` filter have not run on GitHub's runners yet.

## Not done, and why

- `Published.on_the_wall` has callers; the audit's "dead" was wrong, and it stays.
- A work whose only museum page is gone never settles, because the host cannot tell "every
  page gone" from "could not be asked" (wave 2).
- The output-count cap on a client heartbeat is not added (said so in `security-model.md`).

## Consumer note
Operators: read the two items under "What an operator must know" before deploying. A private
source plugin built for 1.4 needs its deadlines declared first. The contract package does not
change, so no `contract-v*` tag is cut, and Arrt Player's pin does not move for this branch.
