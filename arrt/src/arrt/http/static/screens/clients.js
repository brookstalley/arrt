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
 * label panel and the wall it captions. Its name, its token and forgetting it are
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
 * question it asks, for the reason `core/confirm.js` gives. Rotating and forgetting
 * ask first, because each can leave a wall dark: a rotated token refuses the
 * Player holding the old one, and a forgotten Player leaves its walls with nothing
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
import { agree, counted, listed } from "../core/counting.js";
import { dated } from "../core/dates.js";
import { openPanel } from "../core/editing.js";
import { outputCell, screenName } from "../core/outputs.js";
import { playerStateGlyph, playerStateWord } from "../core/states.js";
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
  const waiting = players.filter((player) => statusOf(player).waiting).length;
  // One sentence per fault, though each Player in it carries it: the server's
  // sentence names them all, so it is said once.
  const faults = [...new Set(players.flatMap((player) => player.faults.map((fault) => fault.description)))];

  render(
    generation,
    el("h1", { text: "Players" }),
    el("p", {
      class: "muted page-facts",
      text: pageFacts(players.length, reporting, waiting),
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

/* The one line under the page's name: how many Players, how many report, and
 * how many the page is waiting on for a first report, which is the step a
 * household setting one up is on. "1 Player ·
 * waiting for it to report"; "3 Players · 1 reporting · waiting for 2 to
 * report". */
function pageFacts(count, reporting, waiting) {
  if (!count) return counted(0, "Player");
  if (count === 1 && waiting === 1) return `${counted(1, "Player")} · waiting for it to report`;
  return [counted(count, "Player"), `${reporting} reporting`, waiting ? `waiting for ${waiting} to report` : null].filter(Boolean).join(" · ");
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
              cell("Player", [el("span", { class: "player-name", text: player.name }), settingsLink(player)]),
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

/* Whether the Player is reporting, in a glyph and a word, and what that means
 * for it: the Player's state as the server states it (`state`,
 * `programming/player_state.py`), in the contract's words (`core/states.js`).
 * Nothing here reads the report's age or its problem to decide a state: the
 * server has, against the contract's threshold, so Players, Walls and Status
 * cannot disagree about one Player. A Player with no token, or no report yet,
 * is a step of setting it up, drawn as one and never as a fault. */
function statusOf(player) {
  const state = player.state ? player.state.state : null;
  const status = { glyph: playerStateGlyph(state), word: playerStateWord(state, player.state ? player.state.since : null), more: null, state };
  if (state === "no_token") return { ...status, more: "Admitted nowhere until one is issued, in Edit…" };
  // A token and no report yet: the page is waiting for it, and the words say so
  // and what it waits on, rather than "Never reported", which read as a fault
  // on the evening the Player was added.
  if (state === "awaiting_report") {
    return { ...status, more: "Once it is running with its token, it reports here within a minute or so.", waiting: true };
  }
  if (state === "report_unreadable") return { ...status, more: player.heartbeat.description };
  if (state === "reporting") return { ...status, more: player.heartbeat.description, reporting: true };
  return status;
}

function statusCell(player) {
  const status = statusOf(player);
  return el("div", { class: "player-status", "data-state": status.state || "" }, [
    el("span", { text: `${status.glyph} ${status.word}` }),
    status.more ? el("span", { class: "muted", text: status.more }) : null,
  ]);
}

/* The address of the Player's own settings page, as a link, only where the
 * server served one (`settings_url`, which it serves only when it passes
 * `client-heartbeat.v1`'s check, and null otherwise). Set as the `href` exactly
 * as given, never assembled or mended here; its words are this page's, set as
 * text, and it opens no reference back to this page (`rel`). */
function settingsLink(player) {
  if (typeof player.settings_url !== "string" || !player.settings_url) return null;
  return el("a", {
    class: "link player-settings",
    href: player.settings_url,
    rel: "noopener noreferrer",
    text: "Its settings page",
    "aria-label": `${player.name}'s settings page`,
  });
}

/* A Player's outputs of one kind, as the server states them, in its order. */
function outputsOf(player, kind) {
  const outputs = player.state && Array.isArray(player.state.outputs) ? player.state.outputs : [];
  return outputs.filter((output) => output.kind === kind);
}

/* What the Player's last readable report said of each output, by name: its
 * size, and whether it was connected, for an output the server no longer
 * speaks of as now (`outputCell`'s "was"). Facts of the report, never a state. */
function reportedOf(player, field) {
  const beat = player.heartbeat;
  const readable = beat && !beat.absent && !beat.problem;
  return new Map((readable ? beat[field] || [] : []).map((each) => [each.name, each]));
}

/* Where there is no output of a kind to list, why, from the Player's state:
 * `none` (it reported none), `unreadable`, `stale`, or null (not reported yet). */
function noneWhy(player) {
  const state = player.state ? player.state.state : null;
  if (state === "reporting") return "none";
  if (state === "report_unreadable") return "unreadable";
  if (state === "not_heard_from") return "stale";
  return null;
}

const NO_SCREEN_WORDS = {
  none: "It reported no screen.",
  unreadable: "Not known: its last report could not be read.",
  stale: "Not known now: it has not been heard from.",
};

/* Each screen the Player has, its state, and the wall on it; and a wall set on
 * a screen the report does not list, which still shows nothing there. Said in
 * a sentence where there is nothing to list. */
function screensCell(player) {
  const wallsOn = new Map();
  for (const wall of player.walls) wallsOn.set(wall.output, [...(wallsOn.get(wall.output) || []), wall]);
  const states = new Map(outputsOf(player, "display").map((output) => [output.name, output]));
  const names = [...new Set([...states.keys(), ...wallsOn.keys()])];
  if (!names.length) return el("p", { class: "muted", text: NO_SCREEN_WORDS[noneWhy(player)] || "Not reported yet." });
  const reported = reportedOf(player, "outputs");
  return el(
    "ul",
    { class: "player-list" },
    names.map((name) => {
      const said = reported.get(name);
      const output = states.get(name) || { kind: "display", name, state: "awaiting_report", connected: null };
      const size = said && said.screen ? `, ${said.screen[0]} × ${said.screen[1]}` : "";
      const walls = wallsOn.get(name) || [];
      return el("li", {}, [
        el("span", { text: `${screenName(name, said ? said.kind : null)}${size} · ${outputCell(output, player, said ? said.connected : null)}` }),
        el("span", {}, walls.length ? ["Shows ", ...joined(walls.map((wall) => wallLink(wall.wall_id, wall.name)))] : ["No wall"]),
      ]);
    }),
  );
}

/* Each label panel, its state, and the wall it captions: any number of them,
 * on a Player with screens or with none (the owner's ruling 8 of 2026-11-19).
 * Named by its port only where the Player has several, as Walls names it. */
function labelCell(player, wallNames) {
  const records = new Map(player.label_outputs.map((record) => [record.output, record]));
  const states = new Map(outputsOf(player, "label").map((output) => [output.name, output]));
  const names = [...new Set([...states.keys(), ...records.keys()])];
  if (!names.length) {
    return el("p", { class: "muted", text: noneWhy(player) === "none" ? "None reported." : "Not known until it reports." });
  }
  const reported = reportedOf(player, "label_outputs");
  return el(
    "ul",
    { class: "player-list" },
    names.map((name) => {
      const said = reported.get(name);
      const record = records.get(name);
      const output = states.get(name) || { kind: "label", name, state: "awaiting_report", connected: null };
      const port = names.length > 1 ? `${name} · ` : "";
      const size = said && said.size ? `, ${said.size[0]} × ${said.size[1]}` : "";
      return el("li", {}, [
        el("span", { text: `${port}${outputCell(output, player, said ? said.connected : null)}${size}` }),
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

/* Issue a token and show it once, in a dialog of its own. The page behind is
 * repainted first, so the list under the dialog already holds the Player and
 * says it is waiting for its report (not "0 Players" until the dialog
 * closes). A failure is said above the table
 * instead. */
async function issueInto(player, lead = null) {
  let issued;
  try {
    issued = await api(`/api/clients/${encodeURIComponent(player.client_id)}/token`, { method: "POST" });
  } catch (failure) {
    outcome = [lead, failedSentence(`issue a token for ${player.name}`, failure)].filter(Boolean).join(" ");
    await refresh();
    return;
  }
  await refresh();
  tokenOnce(player, issued.token, lead);
}

/* Put `field`'s value on the clipboard. The clipboard API is there only in a
 * secure context, and a household server is often reached over plain http by
 * its address on the network, where it is absent: then the field's own text is
 * selected and copied the older way. Answers whether either worked. */
async function copyFrom(field) {
  if (navigator.clipboard && window.isSecureContext) {
    try {
      await navigator.clipboard.writeText(field.value);
      return true;
    } catch {
      // Refused (a permission, a page not focused): the older way below.
    }
  }
  field.focus();
  field.select();
  try {
    return document.execCommand("copy");
  } catch {
    return false;
  }
}

/* The token, the one time it exists here, and what to do with it.
 *
 * In a read-only field rather than as text, so it is selected whole and copied
 * whole; focused and selected as the dialog opens, with *Copy* beside it. What
 * to do with it is said in the Player's own words: its settings page has
 * *Token* and *Server address* (the Player's own names), so those are the names given, not the
 * environment variables behind them. The address a
 * Player needs is the one this browser reached the server at, which is said as
 * such: a Player on another network may reach it by another name. Then what
 * happens next, so the household knows what this page is waiting for. */
function tokenOnce(player, token, lead) {
  const field = el("input", { type: "text", id: "player-token", readonly: true, value: token, spellcheck: "false", autocomplete: "off" });
  const copied = el("span", { class: "muted token-copied", role: "status" });
  const copy = el("button", {
    class: "action quiet",
    type: "button",
    text: "Copy",
    "aria-label": `Copy ${player.name}'s token`,
    onclick: async () => {
      copied.textContent = (await copyFrom(field))
        ? "Copied."
        : "This browser would not copy it. The token is selected: copy it with the keyboard.";
    },
  });
  openPanel({
    title: `${player.name}'s token`,
    lead,
    body: [
      el("div", { class: "token-once" }, [
        el("p", {
          text: `This is ${player.name}'s new token, and the only time it is shown: only a verifier of it is kept, so copy it now.`,
        }),
        el("div", { class: "row token-row" }, [el("div", { class: "field" }, [el("label", { for: "player-token", text: `Token for ${player.name}` }), field]), copy, copied]),
        el("p", {
          text:
            `On ${player.name}'s own settings page, put this token in Token, and this server's address in ` +
            `Server address, as that Player reaches it — from this browser, ${window.location.origin}. Then save there.`,
        }),
        el("p", {
          text:
            !player.heartbeat || player.heartbeat.absent
              ? `${player.name} is listed under Players, waiting for it to report. Once it is running with this token it reports within a minute or so, and its screens can then be chosen in a wall's Edit…, on Walls.`
              : `Until its settings carry this token, ${player.name} is refused and the walls it shows stop changing; once they do, it reports again within a minute or so.`,
        }),
      ]),
    ],
    closeLabel: "Done",
  });
  field.focus();
  field.select();
}

/* A Player's settings: its name, its token, and forgetting it, last. */
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
      const forgetAct = el("button", {
        class: "action quiet",
        type: "button",
        text: "Forget…",
        "aria-label": `Forget ${player.name}…`,
        onclick: () => {
          panel.close();
          forget(player);
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
          el("div", { class: "panel" }, [el("h3", { text: "Forget" }), el("div", { class: "row" }, [forgetAct])]),
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

async function forget(player) {
  const walls = player.walls.map((wall) => wall.name);
  const captioning = player.label_outputs.filter((label) => label.wall_id).length;
  // Its label panels go with it, so any that caption a wall stop: said, since
  // the walls they caption may be on other Players and stay otherwise as they are.
  const labelsGo = captioning ? ` ${agree(captioning, "Its label panel stops", `Its ${captioning} label panels stop`)} captioning.` : "";
  // A Player never issued a token is admitted nowhere, so there is no token to stop.
  const token = player.token_issued_at ? "Its token stops working at once" : "It has no token";
  const agreed = await confirmAct({
    title: `Forget ${player.name}?`,
    consequence: walls.length
      ? `${token}, and ${listed(walls)} will be left without a Player. ` +
        `${agree(walls.length, "It keeps its theme", "They keep their themes")} until put on another.${labelsGo}`
      : `${token}. It shows no wall, so no wall is affected.${labelsGo}`,
    confirmLabel: `Forget ${player.name}`,
  });
  if (!agreed) return;
  try {
    await api(`/api/clients/${encodeURIComponent(player.client_id)}`, { method: "DELETE" });
    outcome = walls.length
      ? `${player.name} is forgotten. ${counted(walls.length, "wall")} now ${agree(walls.length, "has", "have")} no Player: ${listed(walls)}.`
      : `${player.name} is forgotten. It showed no wall.`;
  } catch (failure) {
    outcome = failedSentence(`forget ${player.name}`, failure);
  }
  await refresh();
}

