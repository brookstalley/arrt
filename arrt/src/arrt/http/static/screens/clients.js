/* Clients — the installed Players this server knows, and which walls each shows.
 *
 * **A page under Settings**, where Radarr keeps Settings › Download Clients: the
 * server's list of the external programs it works with (`clients.md` ruling 1,
 * `information-architecture.md` § The *arr layout). A client is a name and one
 * token; it shows the walls assigned to it, each on one of its outputs, and its
 * host learns them from this server — so assigning a wall here needs no edit on
 * the host.
 *
 * **The token is shown once, and only here.** The server keeps a verifier, so the
 * answer that issued a token is the only place it ever exists outside the host.
 * It is carried across exactly one repaint in `reveal` and dropped as that paint
 * reads it: a reload, or any later act, and it is gone, which is the truth about
 * it rather than a limitation of the page.
 *
 * **Every state is said in words.** No client yet, no token yet, a client that
 * has not reported its outputs, a report that could not be read, a client that
 * reported none, a client showing no wall: each has its own sentence, because
 * each sends the curator somewhere different.
 *
 * **Every act names its client**, in the control's accessible name and in any
 * question it asks, for the reason `core/confirm.js` gives. Rotating and removing
 * ask first, because each can leave a wall dark: a rotated token refuses the
 * Player holding the old one, and a removed client leaves its walls with nothing
 * showing them. Assigning and unassigning do not ask; each is undone by the
 * other, on this page.
 *
 * TEXT IS SET WITH textContent, NEVER innerHTML — the rule is at `core/render.js`,
 * and a client's name and its outputs' names are text somebody else typed.
 */

import { attempt, failedSentence } from "../core/acting.js";
import { api } from "../core/api.js";
import { facts, table } from "../core/badges.js";
import { confirmAct } from "../core/confirm.js";
import { agree, counted } from "../core/counting.js";
import { isStale, screenCell, screenPhrase, STALE_AFTER_SECONDS } from "../core/outputs.js";
import { el, render } from "../core/render.js";
import { refresh } from "../core/router.js";

/* The output kinds `player-contract.md` names, in the words a curator reads. */
const KIND_WORDS = {
  frame: "Samsung Frame",
  framebuffer: "Screen",
};

/* A token just issued, for the one paint that shows it: `{ clientId, token }`. */
let reveal = null;

/* What the last act should leave said, and where the keyboard goes after the
 * repaint it caused: `{ clientId, text }` inside that client's panel, or
 * `{ text }` above the list when the client it was about is gone. */
let outcome = null;

export async function viewClients(generation) {
  const [listing, walls] = await Promise.all([api("/api/clients"), api("/api/walls")]);
  // Read and dropped together, before anything can fail between them: a token
  // that survived into a second paint would be shown twice.
  const shown = reveal;
  const said = outcome;
  reveal = null;
  outcome = null;

  const clients = listing.clients;
  const names = new Map(clients.map((client) => [client.client_id, client.name]));
  const loose = said && !said.clientId ? spoken(said.text) : null;

  render(
    generation,
    el("h1", { text: "Clients" }),
    el("p", {
      class: "muted",
      text:
        "A client is an installed Player. It holds one token, and shows the walls assigned to it here, each on one of " +
        "its outputs. Its host is given this server's address and its token, and learns its walls from this page.",
    }),
    addPanel(),
    loose,
    ...(clients.length
      ? clients.map((client) => clientPanel(client, walls.walls, names, shown, said))
      : [
          el("p", {
            class: "note",
            text: "No client is recorded yet. Add one for each host that runs a Player; its walls are assigned here once it exists.",
          }),
        ]),
  );

  // Only onto a node the paint actually put on the page: `render` declines a
  // paint whose navigation was superseded, and focusing a detached node moves
  // the keyboard nowhere.
  const token = document.getElementById("client-token");
  if (shown && token) {
    token.focus();
    token.select();
    return;
  }
  const status = document.querySelector("#view [data-said]");
  if (said && status) status.focus();
}

/* A sentence an act left behind, announced and focusable. */
function spoken(text) {
  return el("p", { class: "note", role: "status", tabindex: "-1", "data-said": "", text });
}

/* Recording a client, and issuing its token in the same act.
 *
 * A client with no token is admitted nowhere, so a curator adding one always
 * wants the token next; two clicks for one intention would be a step to forget.
 * If the issue fails after the add succeeded, the client is listed with its own
 * "Issue a token", and its panel says the issue failed and why. */
function addPanel() {
  const name = el("input", { type: "text", id: "new-client-name", autocomplete: "off" });
  return el("div", { class: "panel" }, [
    el("h2", { text: "Add a client" }),
    el("div", { class: "row" }, [
      el("div", { class: "field" }, [el("label", { for: "new-client-name", text: "Name of the new client" }), name]),
      el("button", {
        class: "action",
        type: "button",
        text: "Add the client",
        onclick: (event) =>
          attempt(
            event.currentTarget,
            name.value.trim() ? `add ${name.value.trim()}` : "add the client",
            () => api("/api/clients", { method: "POST", body: JSON.stringify({ name: name.value }) }),
            {
              then: async (client) => {
                try {
                  await issue(client);
                } catch (failure) {
                  // The repaint below replaces this panel, so the failure is
                  // said in the new client's own, beside its "Issue a token".
                  outcome = { clientId: client.client_id, text: failedSentence(`issue a token for ${client.name}`, failure) };
                }
                await refresh();
              },
            },
          ),
      }),
    ]),
  ]);
}

async function issue(client) {
  const issued = await api(`/api/clients/${encodeURIComponent(client.client_id)}/token`, { method: "POST" });
  reveal = { clientId: client.client_id, token: issued.token };
}

function clientPanel(client, walls, names, shown, said) {
  const heading = el("h2", { tabindex: "-1", text: client.name });
  return el("section", { class: "panel client", "data-client": client.client_id }, [
    heading,
    shown && shown.clientId === client.client_id ? tokenOnce(client, shown.token) : null,
    said && said.clientId === client.client_id ? spoken(said.text) : null,
    facts([
      [
        "Token",
        client.token_issued_at
          ? `Issued ${when(client.token_issued_at)}`
          : "None issued yet, so it is admitted to nothing until one is.",
      ],
      ["Last report", client.heartbeat.description],
    ]),
    outputs(client),
    shownWalls(client),
    assignForm(client, walls, names),
    acts(client),
  ]);
}

function when(iso) {
  return new Date(iso).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
}

/* The token, the one time it exists here, and what to do with it.
 *
 * In a read-only field rather than as text, so it is selected whole and copied
 * whole; focused and selected by the paint that shows it. The address a host
 * needs is the one this browser reached the server at, which is said as such:
 * a Player on another network may reach it by another name. */
function tokenOnce(client, token) {
  return el("div", { class: "note token-once" }, [
    el("p", {
      text: `This is ${client.name}'s new token, and the only time it is shown: only a verifier of it is kept, so copy it now.`,
    }),
    el("div", { class: "field" }, [
      el("label", { for: "client-token", text: `Token for ${client.name}` }),
      el("input", { type: "text", id: "client-token", readonly: true, value: token, spellcheck: "false", autocomplete: "off" }),
    ]),
    el("p", {
      text:
        `In the Player's settings on ${client.name}'s host, set CLIENT_TOKEN to this token, and SERVER_URL to this ` +
        `server's address as that host reaches it — from this browser, ${window.location.origin}.`,
    }),
  ]);
}

/* What the client last said about its outputs.
 *
 * Three ways to have nothing to list, and each is its own sentence: never
 * reported, reported something unreadable, and reported that it has no outputs.
 * The first two are already the facts' "Last report", so here they say what that
 * means for choosing an output. */
function outputs(client) {
  const beat = client.heartbeat;
  let body;
  if (beat.absent) {
    body = el("p", { class: "muted", text: `${client.name} has not reported its outputs yet, so none can be listed.` });
  } else if (beat.problem) {
    body = el("p", { class: "muted", text: `${client.name}'s last report could not be read, so its outputs are not known.` });
  } else if (!beat.outputs.length) {
    body = el("p", { class: "muted", text: `${client.name} reported that it has no outputs.` });
  } else {
    const stale = isStale(beat);
    body = table(
      `The outputs ${client.name} last reported.`,
      ["Output", "Kind", "Screen", "Size"],
      beat.outputs.map((output) => [
        output.name,
        KIND_WORDS[output.kind] || output.kind,
        screenCell(output, stale),
        output.screen ? `${output.screen[0]} × ${output.screen[1]}` : "size unknown",
      ]),
    );
    // Said once above the table rather than in every row: it is one fact about
    // the report, and Walls reads the same threshold (`core/outputs.js`).
    if (stale) {
      body = el("div", {}, [
        el("p", {
          class: "note client-stale",
          text:
            `${client.name}'s report is older than ${STALE_AFTER_SECONDS / 60} minutes, three missed reports, ` +
            "so whether a screen is on each output now is not known.",
        }),
        body,
      ]);
    }
  }
  return el("div", { class: "client-outputs" }, [el("h3", { text: "Outputs" }), body]);
}

function shownWalls(client) {
  return el("div", { class: "client-walls" }, [
    el("h3", { text: "Walls assigned to it" }),
    client.walls.length
      ? el(
          "ul",
          { class: "client-wall-list" },
          client.walls.map((wall) =>
            el("li", {}, [
              el("span", { text: `${wall.name}, on ${wall.output}` }),
              el("button", {
                class: "action quiet",
                type: "button",
                text: `Unassign ${wall.name}`,
                "aria-label": `Unassign ${wall.name} from ${client.name}`,
                onclick: (event) =>
                  attempt(
                    event.currentTarget,
                    `unassign ${wall.name} from ${client.name}`,
                    () => api(`/api/walls/${encodeURIComponent(wall.wall_id)}/client`, { method: "DELETE" }),
                    {
                      then: async () => {
                        outcome = {
                          clientId: client.client_id,
                          text: `${wall.name} is no longer assigned to ${client.name}. It keeps its theme.`,
                        };
                        await refresh();
                      },
                    },
                  ),
              }),
            ]),
          ),
        )
      : el("p", { class: "muted", text: `${client.name} has no wall assigned yet.` }),
  ]);
}

/* Placing a wall on one of this client's outputs.
 *
 * The output is chosen from what the client last reported where there is a
 * readable report with outputs in it, and typed otherwise — a client being set
 * up before its first run has reported nothing, and the server keeps the
 * assignment either way, with a notice that is shown here. An output already
 * showing a wall is listed with that wall's name: the server refuses a second,
 * and says so in the banner, so the choice is not hidden from a curator who
 * means to unassign the other next. */
function assignForm(client, walls, names) {
  const id = client.client_id;
  const candidates = walls.filter((wall) => wall.client_id !== id);
  const heading = el("h3", { text: "Assign a wall" });
  if (!candidates.length) {
    return el("div", { class: "client-assign" }, [
      heading,
      el("p", {
        class: "muted",
        text: walls.length ? `Every wall is already assigned to ${client.name}.` : "No wall is recorded, so there is nothing to assign.",
      }),
    ]);
  }

  const wallPicker = el("select", { id: `assign-wall-${id}`, "aria-label": `Wall for ${client.name}` });
  for (const wall of candidates) {
    const elsewhere = wall.client_id ? `, now assigned to ${names.get(wall.client_id) || "another client"} on ${wall.output}` : "";
    wallPicker.append(el("option", { value: wall.wall_id, text: `${wall.name}${elsewhere}` }));
  }

  const beat = client.heartbeat;
  const reported = !beat.absent && !beat.problem && beat.outputs.length ? beat.outputs : null;
  const occupied = new Map(client.walls.map((wall) => [wall.output, wall.name]));
  const stale = isStale(beat);
  let output;
  let guidance = null;
  if (reported) {
    output = el("select", { id: `assign-output-${id}`, "aria-label": `Output of ${client.name}` });
    // The first output showing nothing is the one offered, since the server
    // refuses a second wall on an output that already has one.
    const free = reported.find((each) => !occupied.has(each.name));
    for (const each of reported) {
      const showing = occupied.has(each.name) ? `, has ${occupied.get(each.name)}` : "";
      output.append(
        el("option", { value: each.name, text: `${each.name} (${screenPhrase(each, stale)}${showing})`, selected: each === free }),
      );
    }
  } else {
    output = el("input", {
      type: "text",
      id: `assign-output-${id}`,
      placeholder: "hdmi-a-1",
      autocomplete: "off",
      "aria-label": `Output of ${client.name}`,
    });
    guidance = el("p", { class: "muted", text: unreportedSentence(client) });
  }

  return el("div", { class: "client-assign" }, [
    heading,
    guidance,
    el("div", { class: "row" }, [
      el("div", { class: "field" }, [el("label", { for: `assign-wall-${id}`, text: "Wall" }), wallPicker]),
      el("div", { class: "field" }, [el("label", { for: `assign-output-${id}`, text: "Output" }), output]),
      el("button", {
        class: "action",
        type: "button",
        text: `Assign to ${client.name}`,
        onclick: (event) => assign(event.currentTarget, client, wallPicker, output, candidates),
      }),
    ]),
  ]);
}

function unreportedSentence(client) {
  const beat = client.heartbeat;
  const why = beat.absent
    ? `${client.name} has not reported its outputs yet`
    : beat.problem
      ? `${client.name}'s last report could not be read`
      : `${client.name} reported no outputs`;
  return `${why}, so type the name of the output that will show the wall, as the Player names it — for example hdmi-a-1.`;
}

function assign(control, client, wallPicker, output, candidates) {
  const wall = candidates.find((each) => each.wall_id === wallPicker.value);
  return attempt(
    control,
    `assign ${wall.name} to ${client.name}`,
    () =>
      api(`/api/walls/${encodeURIComponent(wall.wall_id)}/client`, {
        method: "POST",
        body: JSON.stringify({ client_id: client.client_id, output: output.value }),
      }),
    {
      then: async (answer) => {
        const placed = `${wall.name} is now assigned to ${client.name} on ${answer.wall.output}.`;
        // The server's notice, when there is one, is the part the curator has
        // to act on, so it is said after the fact it qualifies rather than in
        // its place.
        outcome = { clientId: client.client_id, text: answer.notice ? `${placed} ${answer.notice}` : placed };
        await refresh();
      },
    },
  );
}

function acts(client) {
  const id = client.client_id;
  const rename = el("input", { type: "text", id: `rename-client-${id}`, value: client.name, "aria-label": `Name of ${client.name}` });
  return el("div", { class: "row client-acts" }, [
    el("div", { class: "field" }, [el("label", { for: `rename-client-${id}`, text: "Name" }), rename]),
    el("button", {
      class: "action quiet",
      type: "button",
      text: "Rename",
      "aria-label": `Rename ${client.name}`,
      onclick: (event) =>
        attempt(
          event.currentTarget,
          `rename ${client.name}`,
          () => api(`/api/clients/${encodeURIComponent(id)}`, { method: "POST", body: JSON.stringify({ name: rename.value }) }),
          {
            then: async (renamed) => {
              outcome = { clientId: id, text: `${client.name} is now called ${renamed.name}. Its token and its walls are unchanged.` };
              await refresh();
            },
          },
        ),
    }),
    client.token_issued_at
      ? el("button", {
          class: "action quiet",
          type: "button",
          text: "Rotate the token",
          "aria-label": `Rotate ${client.name}'s token`,
          onclick: (event) => rotate(event.currentTarget, client),
        })
      : el("button", {
          class: "action quiet",
          type: "button",
          text: "Issue a token",
          "aria-label": `Issue a token for ${client.name}`,
          onclick: (event) => attempt(event.currentTarget, `issue a token for ${client.name}`, () => issue(client), { then: () => refresh() }),
        }),
    el("button", {
      class: "action quiet",
      type: "button",
      text: "Remove",
      "aria-label": `Remove ${client.name}`,
      onclick: (event) => remove(event.currentTarget, client),
    }),
  ]);
}

async function rotate(control, client) {
  const agreed = await confirmAct({
    title: `Rotate ${client.name}'s token?`,
    // The consequence that matters is the dark wall, so it leads.
    consequence:
      `${client.name}'s Player is refused from the moment the new token is issued until its settings carry it, ` +
      "so the walls assigned to it stop changing until then. The new token is shown once, here.",
    confirmLabel: "Rotate the token",
  });
  if (!agreed) return;
  await attempt(control, `rotate ${client.name}'s token`, () => issue(client), { then: () => refresh() });
}

async function remove(control, client) {
  const walls = client.walls.map((wall) => wall.name);
  const agreed = await confirmAct({
    title: `Remove ${client.name}?`,
    consequence: walls.length
      ? `Its token stops working at once, and ${listed(walls)} will be left without a client. ` +
        `${agree(walls.length, "It keeps its theme", "They keep their themes")} until assigned to another.`
      : "Its token stops working at once. No wall is assigned to it, so no wall is affected.",
    confirmLabel: `Remove ${client.name}`,
  });
  if (!agreed) return;
  await attempt(control, `remove ${client.name}`, () => api(`/api/clients/${encodeURIComponent(client.client_id)}`, { method: "DELETE" }), {
    then: async () => {
      outcome = {
        text: walls.length
          ? `${client.name} is removed. ${counted(walls.length, "wall")} now ${agree(walls.length, "has", "have")} no client: ${listed(walls)}.`
          : `${client.name} is removed. It showed no wall.`,
      };
      await refresh();
    },
  });
}

/* "Study", "Study and Hall", "Study, Hall and Landing". */
function listed(names) {
  if (names.length < 2) return names.join("");
  return `${names.slice(0, -1).join(", ")} and ${names[names.length - 1]}`;
}
