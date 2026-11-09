---
schema: 1
type: feat
scope: mcp-household-agents
date: 2026-11-08
title: The taste brief over MCP, and Host and Origin checked on every surface but the Player's
---

`agents-and-memory.md` item 3, so a household's own agent can work against its Arrt
over MCP from inside the LAN. Open question 5 was answered from the code: taste
writes (`art_taste` `set` and `delete`) and verdicts (`art_review(action='set_verdict')`,
which writes observed taste by the owner's rule) were already on MCP. Two things were
missing:
- **`art_taste(action='brief')`** returns the taste as the text Ask's prompt and
  discovery's phase 1 are told, from `TasteService.brief()`.
- **`arrt.http.hosts.HostGuard`** wraps the whole application. It refuses a request
  whose `Host` is not `localhost`, an IP address, or a name in the new
  `CURATION_ALLOWED_HOSTS` (`421`), and one whose `Origin`, when sent, fails the same
  test (`403`).

  The Player's routes, read from the router that mounts them, are exempt, because
  they take the wall's token. This closes the DNS-rebinding vector #53 recorded
  against `/mcp` and `/api`. Binding policy could not close it, because the
  reference deployment publishes the server's port directly for its Player.

## Consumer note

Arrt now refuses requests for a name it was not told about, so a web page cannot
take it over through your browser. **If you reach Arrt by a name** (for example
through a reverse proxy), list that name in `CURATION_ALLOWED_HOSTS` before
upgrading, or the browser interface and MCP will refuse you, saying which setting
to change. Reaching it by IP address needs nothing. The walls are not affected.
Agents connected over MCP can now ask for the curator's taste in the same words
Arrt's own assistant is given.
