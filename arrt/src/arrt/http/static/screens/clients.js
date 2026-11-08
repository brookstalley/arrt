/* Players — the devices at the walls this server knows, one row each.
 *
 * **A page under Settings**, where Radarr keeps Settings › Download Clients: the
 * server's list of the external programs it works with (`clients.md` ruling 1,
 * `information-architecture.md` § The *arr layout). A Player is a name and one
 * token. The server's records, routes and tools call it a client, a contract
 * with what calls them; a person reads *Player* (§ Vocabulary).
 *
 * **What is true now, and its settings one step away** (`design-direction.md`
 * § Component Patterns, "How a page reads"; ruling 7 of 2026-10-27). A row says
 * whether the Player is reporting, its screens and the wall on each, and its
 * label panel and the wall it captions. Its name, its token and removing it are
 * its *Edit…*. Which wall a screen or a panel shows is the wall's setting, so it
 * is set in the wall's own *Edit…* on Walls, and this page only says it.
 *
 * **The token is shown once, in the dialog that issued it.** The server keeps a
 * verifier, so that answer is the only place the token ever exists outside the
 * Player. Closing the dialog, or a reload, and it is gone, which is the truth
 * about it rather than a limitation of the page.
 *
 * **Every state is said in words.** No Player yet, no token yet, never reported,
 * a report that could not be read, one too old to speak for now, a Player that
 * reported no screen: each has its own words, because each sends the curator
 * somewhere different.
 *
 * **Every act names its Player**, in the control's accessible name and in any
 * question it asks, for the reason `core/confirm.js` gives. Rotating and removing
 * ask first, because each can leave a wall dark: a rotated token refuses the
 * Player holding the old one, and a removed Player leaves its walls with nothing
 * showing them.
 *
 * TEXT IS SET WITH textContent, NEVER innerHTML — the rule is at `core/render.js`,
 * and a Player's name and its outputs' names are text somebody else typed.
 */

import { attempt, failedSentence } from "../core/acting.js";
import { api } from "../core/api.js";
import { facts } from "../core/badges.js";
import { GLYPHS } from "../core/glyphs.js";
import { confirmAct } from "../core/confirm.js";
import { agree, counted } from "../core/counting.js";
import { dated } from "../core/dates.js";
import { openPanel } from "../core/editing.js";
import { isStale, screenCell, screenName } from "../core/outputs.js";
import { el, emptyState, render } from "../core/render.js";
import { wallLink } from "../core/places.js";
import { refresh } from "../core/router.js";
import { state } from "../core/state.js";
import { toolbar } from "../core/toolbar.js";

/* What the last act should leave said, above the table, across the repaint it
 * caused. */
let outcome = null;

export async function viewClients(generation) {
  // The walls come along for the label panels: a panel may caption a wall on
  // another Player, which this Player's own listing does not name.
  const [listing, walls] = await Promise.all([api("/api/clients"), api("/api/walls")]);
  const wallNames = new Map(walls.walls.map((wall) => [wall.wall_id, wall.name]));
  const said = outcome;
  outcome = null;

  const players = listing.clients;
  // Arrived at by its address (`#clients?client=<id>`), which kept its spelling
  // when the page became Players, as every renamed page's has.
  const asked = state.params.client;
  const reporting = players.filter((player) => statusOf(player).reporting).length;
  // One sentence per fault, though each Player in it carries it: the server's
  // sentence names them all, so it is said once.
  const faults = [...new Set(players.flatMap((player) => player.faults.map((fault) => fault.description)))];

  render(
    generation,
    el("h1", { text: "Players" }),
    el("p", {
      class: "muted page-facts",
      text: players.length ? `${counted(players.length, "Player")} · ${reporting} reporting` : counted(0, "Player"),
    }),
    toolbar({ actions: [addOpener()] }),
    said ? spoken(said) : null,
    players.length
      ? playersTable(players, asked, wallNames)
      : emptyState(
          "No Player is recorded yet.",
          "Add one for each Player at a wall. Which wall it shows is set in that wall's Edit…, on Walls.",
        ),
    ...faults.map((text) => el("p", { class: "note player-fault", text: `${GLYPHS.problem} ${text}` })),
  );

  const status = document.querySelector("#view [data-said]");
  if (said && status) status.focus();
}

/* A sentence an act left behind, announced and focusable. */
function spoken(text) {
  return el("p", { class: "note", role: "status", tabindex: "-1", "data-said": "", text });
}

/* One row per Player. Built here rather than with `badges.js`' `table`, because
 * a row carries what that helper's rows cannot: the Player it is, for an
 * address that asks for it, and its *Edit…*. The same classes, so a phone reads
 * each row as a card under its columns' names. */
function playersTable(players, asked, wallNames) {
  const headers = ["Player", "Status", "Screens", "Label panel"];
  const cell = (label, children) => el("td", { "data-label": label }, children);
  return el("div", { class: "table-scroll" }, [
    el("table", { class: "stacked players" }, [
      el("caption", { text: "Players this server knows." }),
      el("thead", {}, [
        el("tr", {}, [
          ...headers.map((header) => el("th", { scope: "col", text: header })),
          el("th", { scope: "col" }, [el("span", { class: "visually-hidden", text: "Settings" })]),
        ]),
      ]),
      el(
        "tbody",
        {},
        players.map((player) =>
          el(
            "tr",
            {
              "data-player": player.client_id,
              tabindex: asked === player.client_id ? "-1" : null,
              "data-arrive": asked === player.client_id,
            },
            [
              cell("Player", [el("span", { class: "player-name", text: player.name })]),
              cell("Status", [statusCell(player)]),
              cell("Screens", [screensCell(player)]),
              cell("Label panel", [labelCell(player, wallNames)]),
              el("td", { class: "player-edit" }, [editOpener(player)]),
            ],
          ),
        ),
      ),
    ]),
  ]);
}

/* Whether the Player is reporting, in a glyph and a word, and the age of what
 * it last said. A Player with no token is admitted nowhere, so that is its
 * state whatever an old report says. */
function statusOf(player) {
  const beat = player.heartbeat;
  if (!player.token_issued_at) return { glyph: GLYPHS.none, word: "No token", more: "Admitted nowhere until one is issued, in Edit…" };
  if (beat.absent) return { glyph: GLYPHS.none, word: "Never reported", more: null };
  if (beat.problem) return { glyph: GLYPHS.problem, word: "Report unreadable", more: beat.description };
  if (isStale(beat)) return { glyph: GLYPHS.waiting, word: `Not heard from since ${dated(beat.reported_at)}`, more: null };
  return { glyph: GLYPHS.good, word: "Reporting", more: beat.description, reporting: true };
}

function statusCell(player) {
  const status = statusOf(player);
  return el("div", { class: "player-status" }, [
    el("span", { text: `${status.glyph} ${status.word}` }),
    status.more ? el("span", { class: "muted", text: status.more }) : null,
  ]);
}

/* Each screen the Player reported, its state, and the wall on it; and a wall
 * set on a screen the report does not list, which still shows nothing there.
 * Said in a sentence where there is nothing to list. */
function screensCell(player) {
  const beat = player.heartbeat;
  const readable = !beat.absent && !beat.problem;
  const reported = readable ? beat.outputs : [];
  const stale = isStale(beat);
  const wallsOn = new Map();
  for (const wall of player.walls) wallsOn.set(wall.output, [...(wallsOn.get(wall.output) || []), wall]);
  const names = [...new Set([...reported.map((each) => each.name), ...wallsOn.keys()])];
  if (!names.length) {
    const why = beat.absent
      ? "Not reported yet."
      : beat.problem
        ? "Not known: its last report could not be read."
        : "It reported no screen.";
    return el("p", { class: "muted", text: why });
  }
  const byName = new Map(reported.map((each) => [each.name, each]));
  return el(
    "ul",
    { class: "player-list" },
    names.map((name) => {
      const output = byName.get(name);
      const size = output && output.screen ? `, ${output.screen[0]} × ${output.screen[1]}` : "";
      const state = output ? screenCell(output, stale) : `${GLYPHS.waiting} not in its last report`;
      const walls = wallsOn.get(name) || [];
      return el("li", {}, [
        el("span", { text: `${screenName(name, output ? output.kind : null)}${size} · ${state}` }),
        el("span", {}, walls.length ? ["Shows ", ...joined(walls.map((wall) => wallLink(wall.wall_id, wall.name)))] : ["No wall"]),
      ]);
    }),
  );
}

/* Each label panel, whether it is answering, and the wall it captions. Named by
 * its port only where the Player has several, as Walls names it. */
function labelCell(player, wallNames) {
  const beat = player.heartbeat;
  const readable = !beat.absent && !beat.problem;
  const reported = readable ? beat.label_outputs || [] : [];
  const stale = isStale(beat);
  const records = new Map(player.label_outputs.map((record) => [record.output, record]));
  const names = [...new Set([...reported.map((each) => each.name), ...records.keys()])];
  if (!names.length) {
    return el("p", { class: "muted", text: readable ? "None reported." : "Not known until it reports." });
  }
  const byName = new Map(reported.map((each) => [each.name, each]));
  return el(
    "ul",
    { class: "player-list" },
    names.map((name) => {
      const each = byName.get(name);
      const record = records.get(name);
      const port = names.length > 1 ? `${name} · ` : "";
      const size = each && each.size ? `, ${each.size[0]} × ${each.size[1]}` : "";
      const state = each ? panelState(each, stale) : `${GLYPHS.waiting} not in its last report`;
      return el("li", {}, [
        el("span", { text: `${port}${state}${size}` }),
        el("span", {}, record && record.wall_id ? ["Captions ", captionedWall(record.wall_id, wallNames)] : ["No wall"]),
      ]);
    }),
  );
}

/* A label may caption a wall on any Player, so it is named from the walls'
 * own listing. One that listing does not hold is said as one rather than drawn
 * as a link with no words in it. */
function captionedWall(wallId, wallNames) {
  return wallNames.has(wallId) ? wallLink(wallId, wallNames.get(wallId)) : "a wall this page could not name";
}

/* A panel's state. Not answering is a panel that would not open or whose last
 * draw failed, which is a fault, unlike a television switched off. */
function panelState(output, stale) {
  if (stale) return `${GLYPHS.waiting} not known now (was ${output.connected ? "answering" : "not answering"})`;
  return output.connected ? `${GLYPHS.good} answering` : `${GLYPHS.problem} not answering`;
}

function joined(nodes) {
  return nodes.flatMap((node, at) => (at ? [", ", node] : [node]));
}

/* *Add Player…*: its name, and its token issued in the same act, since a Player
 * with no token is admitted nowhere. If the issue fails after the add, the
 * Player is listed with *Issue a token* in its *Edit…*, and the sentence above
 * the table says why. */
function addOpener() {
  return el("button", {
    class: "action quiet",
    type: "button",
    text: "Add Player…",
    "aria-haspopup": "dialog",
    onclick: () => {
      const nameId = "new-player-name";
      const name = el("input", { id: nameId, type: "text", autocomplete: "off", placeholder: "Hall Pi" });
      let panel = null;
      const add = el("button", {
        class: "action",
        type: "button",
        text: "Add Player",
        onclick: (event) =>
          attempt(
            event.currentTarget,
            name.value.trim() ? `add ${name.value.trim()}` : "add the Player",
            () => api("/api/clients", { method: "POST", body: JSON.stringify({ name: name.value }) }),
            {
              then: async (player) => {
                panel.close();
                await issueInto(player, `${player.name} is added.`);
              },
            },
          ),
      });
      panel = openPanel({
        title: "Add a Player",
        lead: "A Player is the device at a wall. Its token is issued as it is added and shown once. Which wall it shows is set in that wall's Edit…, on Walls.",
        closeLabel: "Cancel",
        body: [el("div", { class: "field" }, [el("label", { for: nameId, text: "Name" }), name])],
        actions: [add],
      });
      name.focus();
    },
  });
}

/* Issue a token and show it once, in a dialog of its own; the page repaints
 * when that dialog closes. A failure is said above the table instead. */
async function issueInto(player, lead = null) {
  let issued;
  try {
    issued = await api(`/api/clients/${encodeURIComponent(player.client_id)}/token`, { method: "POST" });
  } catch (failure) {
    outcome = [lead, failedSentence(`issue a token for ${player.name}`, failure)].filter(Boolean).join(" ");
    await refresh();
    return;
  }
  tokenOnce(player, issued.token, lead);
}

/* The token, the one time it exists here, and what to do with it.
 *
 * In a read-only field rather than as text, so it is selected whole and copied
 * whole; focused and selected as the dialog opens. The address a Player needs
 * is the one this browser reached the server at, which is said as such: a
 * Player on another network may reach it by another name. */
function tokenOnce(player, token, lead) {
  const field = el("input", { type: "text", id: "player-token", readonly: true, value: token, spellcheck: "false", autocomplete: "off" });
  openPanel({
    title: `${player.name}'s token`,
    lead,
    body: [
      el("div", { class: "token-once" }, [
        el("p", {
          text: `This is ${player.name}'s new token, and the only time it is shown: only a verifier of it is kept, so copy it now.`,
        }),
        el("div", { class: "field" }, [el("label", { for: "player-token", text: `Token for ${player.name}` }), field]),
        el("p", {
          text:
            `In ${player.name}'s settings, set CLIENT_TOKEN to this token, and SERVER_URL to this server's ` +
            `address as that Player reaches it — from this browser, ${window.location.origin}.`,
        }),
      ]),
    ],
    closeLabel: "Done",
    onClose: () => refresh(),
  });
  field.focus();
  field.select();
}

/* A Player's settings: its name, its token, and removing it, last. */
function editOpener(player) {
  return el("button", {
    class: "action quiet",
    type: "button",
    text: "Edit…",
    "aria-label": `Edit ${player.name}…`,
    "aria-haspopup": "dialog",
    onclick: () => {
      let wrote = false;
      let panel = null;
      const nameId = `player-name-${player.client_id}`;
      const field = el("input", { id: nameId, type: "text", value: player.name, autocomplete: "off" });
      const renameButton = el("button", {
        class: "action",
        type: "button",
        text: "Rename",
        "aria-label": `Rename ${player.name}`,
        onclick: (event) =>
          attempt(
            event.currentTarget,
            `rename ${player.name}`,
            () => api(`/api/clients/${encodeURIComponent(player.client_id)}`, { method: "POST", body: JSON.stringify({ name: field.value }) }),
            {
              then: (renamed) => {
                outcome = `${player.name} is now called ${renamed.name}. Its token and its walls are unchanged.`;
                wrote = true;
                panel.close();
              },
            },
          ),
      });
      const tokenAct = player.token_issued_at
        ? el("button", {
            class: "action quiet",
            type: "button",
            text: "Rotate the token…",
            "aria-label": `Rotate ${player.name}'s token…`,
            onclick: () => {
              panel.close();
              rotate(player);
            },
          })
        : el("button", {
            class: "action quiet",
            type: "button",
            text: "Issue a token",
            "aria-label": `Issue a token for ${player.name}`,
            onclick: () => {
              panel.close();
              issueInto(player);
            },
          });
      const removeAct = el("button", {
        class: "action quiet",
        type: "button",
        text: "Remove…",
        "aria-label": `Remove ${player.name}…`,
        onclick: () => {
          panel.close();
          remove(player);
        },
      });
      panel = openPanel({
        title: `Edit ${player.name}`,
        body: [
          el("div", { class: "panel" }, [
            el("h3", { text: "Name" }),
            el("div", { class: "row" }, [el("div", { class: "field" }, [el("label", { for: nameId, text: "Name" }), field]), renameButton]),
          ]),
          el("div", { class: "panel" }, [
            el("h3", { text: "Token" }),
            facts([
              [
                "Token",
                player.token_issued_at ? `Issued ${dated(player.token_issued_at)}` : "None issued yet, so it is admitted to nothing until one is.",
              ],
            ]),
            el("div", { class: "row" }, [tokenAct]),
          ]),
          el("div", { class: "panel" }, [el("h3", { text: "Remove" }), el("div", { class: "row" }, [removeAct])]),
        ],
        onClose: () => {
          if (wrote) refresh();
        },
      });
    },
  });
}

async function rotate(player) {
  const agreed = await confirmAct({
    title: `Rotate ${player.name}'s token?`,
    // The consequence that matters is the dark wall, so it leads.
    consequence:
      `${player.name} is refused from the moment the new token is issued until its settings carry it, ` +
      "so the walls it shows stop changing until then. The new token is shown once.",
    confirmLabel: "Rotate the token",
  });
  if (agreed) await issueInto(player);
}

async function remove(player) {
  const walls = player.walls.map((wall) => wall.name);
  const captioning = player.label_outputs.filter((label) => label.wall_id).length;
  // Its label panels go with it, so any that caption a wall stop: said, since
  // the walls they caption may be on other Players and stay otherwise as they are.
  const labelsGo = captioning ? ` ${agree(captioning, "Its label panel stops", `Its ${captioning} label panels stop`)} captioning.` : "";
  // A Player never issued a token is admitted nowhere, so there is no token to stop.
  const token = player.token_issued_at ? "Its token stops working at once" : "It has no token";
  const agreed = await confirmAct({
    title: `Remove ${player.name}?`,
    consequence: walls.length
      ? `${token}, and ${listed(walls)} will be left without a Player. ` +
        `${agree(walls.length, "It keeps its theme", "They keep their themes")} until put on another.${labelsGo}`
      : `${token}. It shows no wall, so no wall is affected.${labelsGo}`,
    confirmLabel: `Remove ${player.name}`,
  });
  if (!agreed) return;
  try {
    await api(`/api/clients/${encodeURIComponent(player.client_id)}`, { method: "DELETE" });
    outcome = walls.length
      ? `${player.name} is removed. ${counted(walls.length, "wall")} now ${agree(walls.length, "has", "have")} no Player: ${listed(walls)}.`
      : `${player.name} is removed. It showed no wall.`;
  } catch (failure) {
    outcome = failedSentence(`remove ${player.name}`, failure);
  }
  await refresh();
}

/* "Study", "Study and Hall", "Study, Hall and Landing". */
function listed(names) {
  if (names.length < 2) return names.join("");
  return `${names.slice(0, -1).join(", ")} and ${names[names.length - 1]}`;
}
