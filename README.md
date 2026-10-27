# Arrt

*Formerly samsung-frame-art-loader, then Curatarr.*

Curated art for the screens in a house, in the manner of Radarr and Sonarr.

Arrt is the server. It holds two roles:

- **The Library** finds, acquires, maintains, upgrades and enhances artwork,
  including standing "watch for new abstract expressionists" searches.
- **Programming** decides which playlist hangs on which wall, and publishes each
  wall's feed: what to show, when, and the label that goes with it.

It runs as a container on a home NAS, with a browser interface, a JSON API and
an MCP server on one port.

**Each wall is driven by [Arrt Player](https://github.com/brookstalley/arrt-player)**,
in the manner of a Plex client. It pulls its walls' feeds into a local cache and
shows them on whatever screen it owns: a Samsung Frame, a plain LCD, a monitor.
It composes the mat for that screen, and draws the label on an e-paper panel or
as a caption in the mat. A wall goes on showing art while the server is down.

**The contract between the two** is `player-contract.md` and the
`arrt-contract` package under `contract/`, which this repository owns and Arrt
Player pins by tag. How the product got to this shape, and what comes next:
`.prawduct/artifacts/re-architecture.md`.

## Where things are written down

| For | Read |
|---|---|
| Running the tests, the linters, and the server | `CLAUDE.md` |
| Every environment variable, and which are required | `.env.example` |
| Deploying the server, and what each release asks of it | `deploy/README.md` |
| Where it is going, and in what order | `.prawduct/artifacts/re-architecture.md` |
| Why any of it is shaped this way | `.prawduct/artifacts/` |

## Quick start

```sh
cp .env.example .env                       # then set ART_ROOT
cd arrt && uv run python -m arrt --init   # once, to make ART_ROOT an art root
cd arrt && uv run python -m arrt          # every run after that
```

**`--init` is needed once per art root, and leaving it out is the point.** The
server refuses to start against a directory that is neither marked as an art root
nor already holding a catalogue, because the alternative is what it used to do: a
typo in `ART_ROOT` created the directory, created an empty catalogue, and started
cleanly, leaving the operator with a working server and an empty collection. An
existing art root needs nothing — a directory holding a catalogue is one by
better evidence than a marker.

`.env` supplies defaults and an exported variable beats it, so a run against a
scratch tree needs no edit to the file — with the same one-time flag the first
time, since a scratch tree is a new art root:
`ART_ROOT=/tmp/scratch uv run python -m arrt --init`.

Then open `http://127.0.0.1:$CURATION_PORT/` — the browser interface serves the
catalogue, discovery runs, themes, the wall manifest and a health view. MCP
clients connect to `/mcp` on the same port, and the UI's own JSON API answers
under `/api`.
