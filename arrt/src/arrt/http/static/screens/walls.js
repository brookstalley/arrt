/* Walls — what is hanging right now, on each wall.
 *
 * Second in the sidebar, in the slot Sonarr gives its Calendar: the nearest *arr
 * idea to "what is showing when" (`information-architecture.md` § The *arr
 * layout). It was the home page until the library took that place, as it has in
 * every *arr app.
 *
 * **Built to "How a page reads"** (`design-direction.md` § Component Patterns;
 * the owner's rulings of 2026-10-27, `ia-proposal.md`): the page's name, one line
 * of facts, and a toolbar holding the page's acts; then one card per wall.
 *
 * **Each card leads with what the wall's screen is doing** (`labels-and-surfaces.md`
 * § Display state), which the server derives for each wall and `/api/walls`
 * carries as `display_state`, as a badge at the card's head beside the wall's
 * name. Showing art: the work on the wall now, large, with its label facts and a
 * link to its page. A dark screen: the work it showed last, dimmed, or the next
 * one while nothing has been logged (ruling 6 of 2026-10-27). Any other state in
 * plain words, because a screen somebody is watching television on is not a wall
 * with nothing hung. Under the work, the card's acts, **Skip** and **Remove…**;
 * then *Hanging*, whose theme's name is the control that hangs another, and how
 * the wall plays it; then the next three works. Its foot holds the links out:
 * History, and the works it cannot show. What the theme holds in full is the
 * theme's page; this card is about the one work a person in the room is looking
 * at. Which Player and screen show the wall is said only when it is a problem.
 *
 * **One wall is the degenerate case of many, never a special case.** There is one
 * section per wall and no single-wall layout for a second display to replace: with
 * one wall this is one section filling the screen and reads exactly as a
 * single-wall home would, and with three it is three of the same thing.
 *
 * **Every act names its wall**, in the control's accessible name and in any
 * question it asks: the button reads "Skip", and is announced as "Skip the work
 * on the living room" — even while there is one wall and the answer is obvious.
 * A sentence that reads correctly today only because there is one possible
 * target is a sentence that silently becomes wrong.
 *
 * **Nothing on the wall has four named reasons, and they are four branches.** No
 * theme hung, an empty theme, a display plane that has never spoken, and a plane
 * this screen could not reach at all. Each states its own sentence and offers the
 * fix for that reason specifically, because the four lead to four different next
 * moves — one is "choose a theme", one is "put works in the theme you chose", one
 * is "go and look at the appliance", and one is "ask again". A single "nothing is
 * showing" would be true in all four cases and useful in none.
 *
 * The fourth is reached differently from the other three, and that shows in the
 * shape below: the first three are read off responses that *arrived*, and the
 * fourth is a request that did not. That is why it is the one whose sentence
 * names which of the two planes answered.
 *
 * **A report past `STALE_AFTER_SECONDS` says nothing about now** (`core/outputs.js`),
 * and the server calls that wall `silent` past the same threshold. The work a wall
 * last reported is still the best answer to "what is on it", so it still leads
 * the card, under when it was last heard from rather than "On the wall now".
 *
 * **This screen does not poll in the background**, and that is `core/status.js`'s
 * decision applied here rather than a gap. Mean time to detection on this surface
 * is bounded by how often the curator opens the page, and a background timer
 * would add load to a Pi without changing it. The one exception is bounded and
 * asked for: after Skip or *Remove…*, the card watches the wall's
 * display state until it names the next work (`awaitNext`), and replaces only the
 * work it leads with and the next three under it, so the focus stays wherever
 * the curator left it. Any other
 * repaint goes through `refresh()` with no argument: `refresh(true)` moves focus,
 * and a poll that moves focus is the recorded defect this client already shipped
 * once, on the one screen with a decision on it.
 */

import { attempt } from "../core/acting.js";
import { ago, clockTime, inWords, readable } from "../core/dates.js";
import { api } from "../core/api.js";
import { absentImage, facts, table } from "../core/badges.js";
import { confirmAct } from "../core/confirm.js";
import { counted } from "../core/counting.js";
import { DEBUG } from "../core/debug.js";
import { openPanel } from "../core/editing.js";
import { hangTheme } from "../core/hanging.js";
import { GLYPHS } from "../core/glyphs.js";
import { el, emptyState, fill, guard, render } from "../core/render.js";
import { screenName, screenState, STALE_AFTER_SECONDS, wallScreenParts } from "../core/outputs.js";
import { clientLink } from "../core/places.js";
import { link, refresh } from "../core/router.js";
import { state } from "../core/state.js";
import { toolbar } from "../core/toolbar.js";

/* How often the card asks for the wall's heartbeat while it waits for the work
 * after a Skip. The run view's interval, the fastest anything here repaints. */
const WATCH_MS = 2000;

export async function viewWalls(generation) {
  let walls;
  let themes;
  try {
    // The themes come along because hanging is an act against a named wall and
    // the theme control lives on this screen: a picker that had to be fetched
    // when it was opened would be a control that is not there when the curator
    // reaches for it. Selections are left out by the server, so Change never
    // offers one.
    [walls, themes] = await Promise.all([api("/api/walls"), api("/api/themes")]);
  } catch (failure) {
    // The fourth reason, at the only scale it can be stated at when this is what
    // failed: with no wall list there is no wall to say it about.
    render(
      generation,
      heading(),
      ...unreachable(
        `The curation plane did not answer — ${failure.message} — so nothing can be said about any wall. The display plane was not asked.`,
      ),
    );
    return;
  }

  const [beats, shownBy, builds, scenes] = await Promise.all([
    heartbeats(),
    clientListing(),
    Promise.all(walls.walls.map(built)),
    // A scene that cannot be read leaves every wall's card standing: the section
    // says so, and the cards say nothing about a scene they cannot know of.
    api("/api/scenes/live").catch(() => null),
  ]);
  const nows = await Promise.all(walls.walls.map((wall) => nowOn(wall)));

  if (!walls.walls.length) {
    // Not one of the four, and stated rather than left as an empty page: a wall
    // is recorded when the plane first opens the catalogue, so none at all is a
    // fact about the deployment rather than about anybody's curation.
    render(
      generation,
      heading(),
      emptyState(
        "No wall is recorded, so there is nowhere to hang anything.",
        "A wall is created when the plane first opens the catalogue.",
      ),
    );
    return;
  }

  const live = scenes ? scenes.live : null;
  const sections = walls.walls.map((wall, index) => wallSection(wall, builds[index], beats, nows[index], themes.themes, shownBy, live));
  // The live scene, if any, is one line above the cards; assembling one is the
  // Scene… dialog's. Both are painted from the same read, by `paintScene`.
  const scene = { walls: walls.walls, scenes, node: el("section", { class: "scene", "aria-label": "Scene", hidden: true }), panel: null };
  paintScene(scene, scenes);
  render(
    generation,
    heading(),
    pageFacts(walls.walls, nows),
    toolbar({ actions: [addWallOpener(), sceneOpener(scene)] }),
    scene.node,
    el("div", { class: "walls" }, sections),
    walls.walls.some((wall) => !wall.theme) ? takeDownNote() : null,
  );
}

/* The page's heading, at the size every page's `h1` has: Walls is a page
 * among the others, with no larger heading of its own. */
function heading() {
  return el("h1", { text: "Walls" });
}

/* The one line of facts under the page's name: how many walls, and how many
 * are showing art now. Counted from each wall's display state, the same reading
 * its card's badge is drawn from. */
function pageFacts(walls, nows) {
  const showing = nows.filter((now) => now && now.shown && now.shown.state === "showing_art").length;
  return el("p", { class: "muted page-facts", text: `${counted(walls.length, "wall")} · ${showing} showing art now` });
}

/* *Scene…*: the dialog that assembles a scene, or changes the one being
 * assembled. The live one is not in it: that is the line above the cards. */
function sceneOpener(scene) {
  return el("button", {
    class: "action quiet",
    type: "button",
    text: "Scene…",
    "aria-haspopup": "dialog",
    onclick: () => {
      scene.panel = openPanel({
        title: "Scene",
        lead: "Show chosen works on your walls together, for a while. Each wall then goes back to what it hangs.",
        body: [],
        onClose: () => (scene.panel = null),
      });
      paintScene(scene, scene.scenes);
    },
  });
}

/* The fact the MCP surface already states after an unhang, said here too: taking
 * a theme down rewrites no manifest, so the set goes on showing the picture. A
 * curator who read only "nothing is hanging" would take a successful take-down
 * for a failed one — the same inference `activate_theme`'s docstring cites when
 * it argues that hanging must publish immediately.
 *
 * Once, under every section, rather than once per wall: it is one fact about how
 * taking down works, not a property of any particular wall, and three empty rooms
 * would otherwise print it three times. `information-architecture.md` states the
 * general form — a qualifier that applies to every row is a footnote under the
 * block rather than a mark on each row. */
function takeDownNote() {
  return el("p", { class: "note", text: "A wall goes on showing what it was showing until a theme is hung." });
}

/* Which Player shows this wall, said only when it is a problem
 * (`design-direction.md` § Component Patterns, "How a page reads": a setting
 * appears on the page only when it is one). A wall nobody shows is an ordinary
 * state (`clients.md` § The model), and the one where everything else on this
 * card happens to no screen at all; a display two clients report is shown by
 * neither, whatever `client_id` still names. */
function assignmentProblem(wall) {
  if (wall.display && wall.display.fault) {
    return el("p", { class: "note wall-problem wall-fault" }, [
      el("span", { text: `${GLYPHS.problem} ${wall.display.fault.description} ` }),
      link({ view: "clients" }, { text: "See Settings › Clients" }),
    ]);
  }
  if (!wall.client_id) {
    return el("p", { class: "muted wall-problem" }, [
      el("span", { text: "No Player shows this wall. " }),
      link({ view: "clients" }, { text: "Assign it in Settings › Clients" }),
    ]);
  }
  return null;
}

/* Every client by its id, or why they could not be read.
 *
 * A wall carries the id of the client it is assigned to and the output's name;
 * the client's name, and its last report of what is on each output, are in the
 * client listing. Caught here for `heartbeats`' reason:
 * a listing that failed is a fact about what this screen can say of each wall,
 * not a refusal of anything the curator did. */
async function clientListing() {
  try {
    const listing = await api("/api/clients");
    return { byId: new Map(listing.clients.map((client) => [client.client_id, client])) };
  } catch (failure) {
    return { failure: failure.message };
  }
}

/* Which client this wall is assigned to, on which output, and whether a screen
 * is there to show it.
 *
 * "Shown by" only where the client reports a screen detected on that output, in
 * a report young enough to speak for now (`core/outputs.js` says why); otherwise
 * the assignment, and what the report says or why it cannot. */
function assignmentLine(wall, shownBy) {
  // No Player, or a display two clients claim: the card says it, and in the Edit…
  // dialog the Player picker reads None, so this says nothing more (a state is
  // worded once).
  if ((wall.display && wall.display.fault) || !wall.client_id) return null;
  const client = shownBy.byId ? shownBy.byId.get(wall.client_id) : null;
  // A port is named only with `?debug` (the owner's ruling 1 of 2026-10-11),
  // and a screen the lead already calls off is not called off again here.
  const output = DEBUG ? wall.output : null;
  const offSaid = Boolean(wall.display_state && wall.display_state.state === "dark");
  return el(
    "p",
    { class: "muted wall-client" },
    client
      ? wallScreenParts(clientLink(client.client_id, client.name), client.name, output, screenState(client.heartbeat, wall.output), client.heartbeat, { offSaid })
      : [`Assigned to ${output ? `${output} of ` : ""}a client whose name and report could not be read${shownBy.failure ? ` — ${shownBy.failure}` : ""}`],
  );
}

/* Which label outputs caption this wall, and on which client each is.
 *
 * Said only when there is one: most walls have no label, and a line saying so
 * on every card would be noise. Labels are mapped in Settings › Clients, beside
 * the client's other surfaces, and this line links there. */
function labelsLine(wall) {
  if (!wall.labels || !wall.labels.length) return null;
  // A client the server could not name is said as one rather than drawn as a
  // link with no words in it.
  const named = wall.labels.map((label) => [
    // The panel's port only with `?debug`, as the wall's own is.
    DEBUG ? `${label.output} on ` : "a label on ",
    label.client_name ? clientLink(label.client_id, label.client_name) : "a client whose name could not be read",
  ]);
  return el("p", { class: "muted wall-labels" }, [
    el("span", {}, ["Captioned by ", ...listedParts(named), ". "]),
    link({ view: "clients" }, { text: "Change in Settings › Clients" }),
  ]);
}

/* "a", "a and b", "a, b and c", of items that are each a list of parts (text
 * and links). */
function listedParts(items) {
  return items.flatMap((parts, at) => [at === 0 ? "" : at === items.length - 1 ? " and " : ", ", ...parts]);
}

/* Every wall's last observation, or the fact that the reading did not arrive.
 *
 * Caught here rather than left to `guard`, for `core/status.js`'s reason: a
 * health read that failed is not a refusal of anything the curator did, and
 * putting it in the page's error banner would report it as one. It is a fact
 * about what this screen can say, and it belongs in the wall it cannot speak for.
 */
async function heartbeats() {
  try {
    return { byWall: readings(await api("/api/health")) };
  } catch (failure) {
    return { failure: failure.message };
  }
}

/* `walls` absent or the wrong shape leaves every wall with no reading, which
 * lands in the silent branch rather than in a green one. A wall reported as
 * well because its observation could not be found is precisely the failure this
 * product exists to refuse. */
function readings(health) {
  const listed = Array.isArray(health.walls) ? health.walls : [];
  return new Map(listed.map((reading) => [reading.wall_id, reading.heartbeat]));
}

/* The work a wall's display state names, or null where it names none: the
 * work on screen while it is showing art, and for a wall gone silent the work it
 * last reported showing. Null for a picture this wall did not put there, which
 * the server states as `showing_art` with no work. */
function shownWork(shown) {
  if (!shown) return null;
  const said = shown.state === "silent" ? shown.last : shown;
  if (!said || said.state !== "showing_art") return null;
  return typeof said.work_id === "string" && said.work_id ? said.work_id : null;
}

/* What the wall's display state says is on it: the state, the work's id, and
 * the work itself — or why the work could not be read. A work the wall names
 * that the library can no longer answer for (archived since, or a fault) is
 * still what the wall reported, so the card says that rather than nothing.
 *
 * With no work on the screen, the work the wall showed last (`last_shown`, the
 * server's log of what each wall has shown), which a dark screen leads with
 * (the owner's ruling 3 of 2026-10-11). And the next three the wall's schedule
 * puts up (`upcoming`), whatever the screen is doing. */
async function nowOn(wall) {
  const shown = wall.display_state || null;
  const workId = shownWork(shown);
  // A wall no screen shows says that alone: what it showed while it had one
  // is its History's, and a lead must not read as a claim about a screen.
  const lastShown = workId || (shown && shown.state === "unassigned") ? null : wall.last_shown || null;
  const upcoming = wall.upcoming || [];
  const [current, last, next] = await Promise.all([
    workId ? workOf(workId) : {},
    lastShown ? workOf(lastShown.work_id) : null,
    Promise.all(upcoming.map((slot) => workOf(slot.work_id))),
  ]);
  return {
    shown,
    workId,
    ...current,
    last: lastShown ? { showing: lastShown, ...last } : null,
    next: upcoming.map((slot, at) => ({ slot, ...next[at] })),
  };
}

/* One work by id, or why it could not be read. */
async function workOf(workId) {
  try {
    return { work: (await api(`/api/works/${encodeURIComponent(workId)}`)).work };
  } catch (failure) {
    return { failure: failure.message };
  }
}

/* What a theme is putting on one wall, or why that could not be asked.
 *
 * A wall with nothing hanging is asked nothing — the route would refuse, and
 * correctly, because there is no theme to evaluate. */
async function built(wall) {
  if (!wall.theme) return {};
  try {
    return { manifest: await api(`/api/manifest?wall_id=${encodeURIComponent(wall.wall_id)}`) };
  } catch (failure) {
    return { failure: failure.message };
  }
}

/* Which of the four reasons this wall is showing nothing for, or that it is not.
 *
 * **Ordered by what the curator would do about it**, which is the whole point of
 * naming them apart. A wall with no theme is told to hang one whatever the
 * display plane is doing; a theme holding no works is told to fill it. Only once
 * a populated theme is published does whether anything is actually on the wall
 * become a question about the appliance.
 *
 * **`entries.length === 0` with `considered` above zero is deliberately not a
 * fifth reason.** That is a theme whose works were all excluded, and the "Not
 * showing" panel below answers it per work and by name — which is a better answer
 * than any single sentence here could give. */
function reasonFor(wall, build, beats) {
  if (!wall.theme) return "no-theme";
  if (build.failure) return "unreachable";
  if (build.manifest.considered === 0) return "empty-theme";
  if (beats.failure) return "unreachable";
  const beat = beats.byWall.get(wall.wall_id);
  if (!beat || beat.absent || beat.problem) return "silent";
  return "hanging";
}

function wallSection(wall, build, beats, now, themes, shownBy, live) {
  const manifest = build.manifest;
  const reason = reasonFor(wall, build, beats);
  // What the card's acts read the current work from. The lead can be replaced
  // after a Skip without repainting the controls, so they read it here rather
  // than from a value captured when they were drawn.
  const card = { wall, now, lead: nowShowing(wall, now), next: nextUp(wall, now), said: el("p", { class: "wall-said", role: "status" }) };
  return el("section", { class: "wall", "data-wall": wall.wall_id }, [
    // `h2` for the wall and `h3` for what is in it, so the nesting survives a
    // second wall: a reader navigating by heading gets each room with its own
    // work inside it. The badge beside it is the screen's state in one word.
    el("header", { class: "wall-head" }, [
      el("h2", { class: "wall-title", tabindex: "-1", "data-arrive": state.params.wall === wall.wall_id, text: wall.name }),
      stateBadge(wall, now, live),
      // The wall's settings, one step away (the page rules of 2026-10-27).
      el("button", {
        class: "action quiet wall-edit",
        type: "button",
        text: "Edit…",
        "aria-haspopup": "dialog",
        "aria-label": `Edit ${wall.name}…`,
        onclick: () => editWall(wall, manifest, shownBy),
      }),
    ]),
    card.lead,
    // Which Player shows the wall is its configuration, and is said here only
    // when it is a problem: no Player, or a screen two Players claim.
    assignmentProblem(wall),
    // The server's sentence, so Walls and the tool surface say the same thing
    // about a Player that cannot read this server's feed. Under the lead, which
    // leads the card whatever else it has to say.
    wall.feed_notice ? el("p", { class: "note wall-feed" }, [el("span", { text: `${GLYPHS.problem} ${wall.feed_notice}` })]) : null,
    sceneLine(wall, live),
    acts(card, reason, manifest),
    card.said,
    // Said only when none of the theme reaches the wall, which is when it stops
    // the wall's job; otherwise the count of works it cannot show is a link at
    // the card's foot (rule: an exception stays quiet until it blocks).
    manifest && reason !== "empty-theme" && manifest.entries.length === 0 ? summaryLine(manifest) : null,
    ...emptiness(reason, wall, build, beats, themes),
    hangingFacts(wall, themes, manifest),
    card.next,
    footer(wall, manifest),
  ]);
}

/* The screen's state in one word, at the card's head: glyph, word and colour,
 * as every badge is (`design-direction.md` § Component Patterns, Badges). The
 * words are the ruled ones (`information-architecture.md` § Vocabulary). */
const BADGES = {
  showing_art: ["good", "Showing"],
  dark: ["none", "Screen off"],
  in_use: ["waiting", "In use"],
  no_screen: ["problem", "No screen"],
  unassigned: ["problem", "No Player"],
  silent: ["problem", "Not reporting"],
  unreachable: ["unknown", "Not known"],
};

function stateBadge(wall, now, live) {
  const entry = live ? live.walls.find((each) => each.wall_id === wall.wall_id) : null;
  if (entry && entry.reached) return badge("putForward", "Scene", "wall-badge-scene");
  const stateName = now && now.shown ? now.shown.state : wall.client_id ? null : "unassigned";
  if (!stateName) return null;
  const [glyph, word] = BADGES[stateName] || BADGES.unreachable;
  return badge(glyph, word, `wall-badge-${stateName}`);
}

function badge(glyph, word, kind) {
  return el("span", { class: `badge wall-badge ${kind}` }, [el("span", { class: "glyph", "aria-hidden": "true", text: GLYPHS[glyph] }), word]);
}

/* The Scene: a work per wall, shown together over each wall's schedule
 * (`player-contract.md` § Scenes; the owner placed it on Walls, as a
 * collection, 2026-10-26).
 *
 * **Assembled, then applied.** Picking a work for a wall stages it there: the
 * wall's Player fetches and prepares it while the rest are picked, so on Apply
 * every wall switches together instead of a Frame landing ten seconds after the
 * screen beside it. Nothing is shown until Apply, which asks first and names each
 * wall and its work, as hanging names the wall.
 *
 * **Once live, each wall says whether it got there**, from its own heartbeat:
 * showing it, or waiting for the television to be free (the Player never
 * interrupts somebody watching), or not there yet, or why it cannot (its work
 * archived or kept off every wall since it was picked). Apply and Release
 * repaint the page, since every card's scene line changes with them; after
 * Apply the section then watches for the walls to arrive, bounded as a Skip's
 * watch is, and rewrites only those lines. Picks, removals and Discard repaint
 * only the section and put focus back on the control the curator was at.
 *
 * One draft and one live scene, as the builder holds them; the server would
 * take more, and a draft made elsewhere (over MCP) shows here as the draft. */
function paintScene(scene, scenes, focus = null) {
  scene.scenes = scenes;
  // The line above the cards: a live scene, or that the scene could not be read.
  // Hidden otherwise, rather than an empty block between the toolbar and the cards.
  const unread = !scenes;
  scene.node.hidden = !(unread || scenes.live);
  if (unread) {
    fill(scene.node, el("p", { class: "note", text: "This page could not read the scene, so it cannot be shown or changed here. Reload to try again." }));
  } else if (scenes.live) {
    fill(scene.node, ...liveScene(scene, scenes.live));
  }
  if (!scene.panel) return;
  // The dialog: what is being assembled, or that nothing can be while a scene is
  // unreadable. Focusable by script only, so Discard, which removes the control
  // that had focus, can hand it to the dialog's own lead rather than the page.
  const parts = [el("span", { id: "scene-title", class: "visually-hidden", tabindex: "-1", "data-scene-focus": "scene-title", text: "Scene" })];
  if (unread) parts.push(el("p", { class: "note", text: "The scene could not be read. Close this and reload to try again." }));
  else if (scenes.live && !scenes.draft) parts.push(el("p", { class: "muted", text: `${sceneSpan(scenes.live)}. Release it, above the walls, before assembling another.` }));
  else parts.push(...sceneBuilder(scene, scenes.draft));
  fill(scene.panel.body, ...parts);
  if (focus) {
    const target = scene.panel.body.querySelector(`[data-scene-focus="${focus}"]`);
    if (target) target.focus();
  }
}

/* Read the scene again and repaint, keeping focus on `focus`. */
async function repaintScene(scene, focus = null) {
  paintScene(scene, await api("/api/scenes/live"), focus);
}

/* A scene's walls in the order the cards below are in, so a sentence naming
 * them reads in the order the page does. */
function inWallOrder(scene, entries) {
  const order = new Map(scene.walls.map((wall, index) => [wall.wall_id, index]));
  return [...entries].sort((one, other) => (order.get(one.wall_id) ?? Infinity) - (order.get(other.wall_id) ?? Infinity));
}

/* What a live scene's walls are doing, in words, from each wall's heartbeat. */
function reachWords(entry) {
  if (entry.cannot_show) return `${entry.wall_name} cannot show it, so it shows its schedule. ${entry.cannot_show}`;
  if (entry.reached) return `${entry.wall_name} is showing it.`;
  if (entry.screen === "in_use") return `${entry.wall_name} is waiting for the television to be free.`;
  return `${entry.wall_name} has not shown it yet.`;
}

function sceneSpan(live) {
  return live.until ? `Scene until ${clockTime(live.until)}` : "Scene, held until released";
}

function liveScene(scene, live) {
  const entries = inWallOrder(scene, live.walls);
  const names = entries.map((entry) => entry.wall_name).join(" and ");
  return [
    el("p", { class: "scene-span", text: sceneSpan(live) }),
    el(
      "ul",
      { class: "scene-walls" },
      entries.map((entry) =>
        el("li", { "data-wall": entry.wall_id }, [
          el("span", { text: `${entry.title || "A work"} on ` }),
          link({ view: "walls", params: { wall: entry.wall_id } }, { class: "link", text: entry.wall_name }),
          el("span", { class: "scene-reach", text: `: ${reachWords(entry)}` }),
        ]),
      ),
    ),
    el("div", { class: "row" }, [
      el("button", {
        class: "action",
        type: "button",
        text: "Release",
        "aria-label": `Release the scene on ${names}`,
        onclick: (event) =>
          attempt(
            event.currentTarget,
            `release the scene on ${names}`,
            () => api(`/api/scenes/${encodeURIComponent(live.scene_id)}/release`, { method: "POST" }),
            { then: () => refresh() },
          ),
      }),
    ]),
  ];
}

/* The preview lengths offered: a short list, not a typed number, because a
 * scene is a look at a room, and these cover a glance, a while and an evening's
 * hour. Twenty is the default the owner ruled (2026-10-08). */
const PREVIEW_MINUTES = [5, 20, 60];

function sceneBuilder(scene, draft) {
  const pins = draft ? draft.walls : [];
  const parts = [
    el("p", {
      class: "muted",
      text: draft && pins.length
        ? "Preparing the walls. Pick a work for each wall you want in the scene, then apply it."
        : "Pick a work for each wall to show them together, for a while or until you release them.",
    }),
    ...scene.walls.map((wall) => pickRow(scene, draft, wall)),
  ];
  if (draft && pins.length) parts.push(applyControls(scene, draft));
  if (draft) {
    parts.push(
      el("div", { class: "row" }, [
        el("button", {
          class: "action quiet",
          type: "button",
          text: "Discard",
          "aria-label": "Discard the scene being assembled",
          onclick: (event) =>
            attempt(
              event.currentTarget,
              "discard the scene",
              () => api(`/api/scenes/${encodeURIComponent(draft.scene_id)}`, { method: "DELETE" }),
              { then: (left) => paintScene(scene, left, "scene-title") },
            ),
        }),
      ]),
    );
  }
  return parts;
}

/* One wall's row: what is picked for it, and a search for a work to pick. The
 * search reads the held works by title or artist, as Artworks' does. */
function pickRow(scene, draft, wall) {
  const pin = draft ? draft.walls.find((entry) => entry.wall_id === wall.wall_id) : null;
  const inputId = `scene-find-${wall.wall_id}`;
  const query = el("input", { id: inputId, type: "search", "aria-label": `Search your library for ${wall.name}`, "data-scene-focus": `find-${wall.wall_id}` });
  const found = el("ul", { class: "scene-found", "aria-label": `Works found for ${wall.name}` });
  const findButton = el("button", {
    class: "action quiet",
    type: "button",
    text: "Search",
    "aria-label": `Search your library for ${wall.name}`,
    onclick: (event) => findWorks(event.currentTarget, scene, draft, wall, query.value, found),
  });
  query.addEventListener("keydown", (event) => {
    if (event.key === "Enter") {
      event.preventDefault();
      findButton.click();
    }
  });
  return el("div", { class: "scene-wall", "data-wall": wall.wall_id }, [
    el("p", { class: "scene-wall-name", text: wall.name }),
    pin
      ? el("p", { class: "scene-pick" }, [
          el("span", { text: `${pin.title || "A work"} ` }),
          el("button", {
            class: "action quiet",
            type: "button",
            text: "Remove",
            "aria-label": `Remove ${pin.title || "the work"} from the scene on ${wall.name}`,
            onclick: (event) =>
              attempt(
                event.currentTarget,
                `remove ${pin.title || "the work"} from the scene on ${wall.name}`,
                () => api(`/api/scenes/${encodeURIComponent(draft.scene_id)}/pins/${encodeURIComponent(wall.wall_id)}`, { method: "DELETE" }),
                { then: () => repaintScene(scene, `find-${wall.wall_id}`) },
              ),
          }),
        ])
      : el("p", { class: "muted scene-pick", text: "Nothing picked." }),
    // Says what it searches: only the works held, as Artworks' search does
    // (ruling 5 of 2026-10-27). The wall's name is in the field's accessible
    // name, so a reader moving by form field hears which wall each is for.
    el("div", { class: "row" }, [el("div", { class: "field" }, [el("label", { for: inputId, text: "Search your library" }), query]), findButton]),
    found,
  ]);
}

async function findWorks(control, scene, draft, wall, words, found) {
  const asked = words.trim();
  if (!asked) {
    fill(found, el("li", { class: "muted", text: "Type a title or an artist first." }));
    return;
  }
  await attempt(
    control,
    `find works for ${wall.name}`,
    () => api(`/api/works?status=accepted&limit=6&q=${encodeURIComponent(asked)}`),
    {
      then: (page) => {
        if (!page.works.length) {
          fill(found, el("li", { class: "muted", text: `Nothing held matches “${asked}”.` }));
          return;
        }
        fill(
          found,
          ...page.works.map((work) =>
            el("li", {}, [
              el("button", {
                class: "action quiet",
                type: "button",
                text: work.artist ? `${work.title}, ${work.artist.name}` : work.title,
                "aria-label": `Pick ${work.title} for ${wall.name}`,
                onclick: (event) => pick(event.currentTarget, scene, draft, wall, work),
              }),
            ]),
          ),
        );
      },
    },
  );
}

/* Pick a work for a wall. The first pick starts the scene, so a visit that
 * picks nothing leaves nothing behind. A refusal (a work that cannot go on a
 * wall) is said beside the work, and the wall's other pick stays. */
function pick(control, scene, draft, wall, work) {
  return attempt(
    control,
    `pick ${work.title} for ${wall.name}`,
    async () => {
      const id = draft ? draft.scene_id : (await api("/api/scenes", { method: "POST" })).scene_id;
      return api(`/api/scenes/${encodeURIComponent(id)}/pins/${encodeURIComponent(wall.wall_id)}`, {
        method: "PUT",
        body: JSON.stringify({ work_id: work.artwork_id }),
      });
    },
    { then: () => repaintScene(scene, `find-${wall.wall_id}`) },
  );
}

function applyControls(scene, draft) {
  const lengthId = "scene-length";
  const length = el(
    "select",
    { id: lengthId },
    PREVIEW_MINUTES.map((minutes) => el("option", { value: String(minutes), text: `${minutes} minutes`, selected: minutes === 20 })),
  );
  const named = inWallOrder(scene, draft.walls)
    .map((entry) => `${entry.title || "a work"} on ${entry.wall_name}`)
    .join(", ");
  const apply = (control, lifetime) => {
    const minutes = Number(length.value);
    const span = lifetime === "hold" ? "until you release it" : `for ${minutes} minutes, then each wall returns to its schedule`;
    return confirmAct({
      title: lifetime === "hold" ? "Hold this scene?" : "Show this scene now?",
      consequence: `${named}, ${span}.`,
      confirmLabel: lifetime === "hold" ? "Hold" : "Apply",
    }).then((yes) =>
      yes
        ? attempt(
            control,
            `apply the scene (${named})`,
            () =>
              api(`/api/scenes/${encodeURIComponent(draft.scene_id)}/apply`, {
                method: "POST",
                body: JSON.stringify(lifetime === "hold" ? { lifetime } : { lifetime, minutes }),
              }),
            {
              then: (applied) => {
                // The dialog's work is done: what the walls do next is the line
                // above the cards, which the watch repaints.
                if (scene.panel) scene.panel.close();
                return watchScene(scene, applied.scene_id);
              },
            },
          )
        : false,
    );
  };
  return el("div", { class: "row scene-apply" }, [
    el("div", { class: "field" }, [el("label", { for: lengthId, text: "Preview length" }), length]),
    el("button", { class: "action", type: "button", text: "Apply", "aria-label": `Apply the scene: ${named}`, onclick: (event) => apply(event.currentTarget, "preview") }),
    el("button", { class: "action quiet", type: "button", text: "Hold", "aria-label": `Hold the scene until released: ${named}`, onclick: (event) => apply(event.currentTarget, "hold") }),
  ]);
}

/* After Apply: repaint the cards once, then watch the scene until every wall
 * reports it, repainting only this section. Bounded as a Skip's watch is, by
 * `STALE_AFTER_SECONDS` and by leaving the screen. */
async function watchScene(scene, sceneId) {
  await refresh();
  const generation = state.poll;
  const deadline = Date.now() + STALE_AFTER_SECONDS * 1000;
  while (Date.now() < deadline) {
    await new Promise((resolve) => setTimeout(resolve, WATCH_MS));
    const section = document.querySelector("section.scene");
    if (state.poll !== generation || !section) return;
    let scenes;
    try {
      scenes = await api("/api/scenes/live");
    } catch {
      return;
    }
    if (!scenes.live || scenes.live.scene_id !== sceneId) return;
    for (const entry of scenes.live.walls) {
      const line = section.querySelector(`li[data-wall="${entry.wall_id}"] .scene-reach`);
      if (line) line.textContent = `: ${reachWords(entry)}`;
    }
    if (scenes.live.walls.every((entry) => entry.reached || entry.cannot_show)) return;
  }
}

/* On a wall's card, while a scene shows here: what the scene put up and until
 * when, beside Skip, because Skip then moves the schedule beneath the scene and
 * nothing on the wall changes until the scene ends. */
function sceneLine(wall, live) {
  const entry = live ? live.walls.find((each) => each.wall_id === wall.wall_id) : null;
  // A wall that cannot show its scene's work shows its schedule, so its card
  // has no scene to speak of; the Scene section says why.
  if (!entry || entry.cannot_show) return null;
  const until = live.until ? `until ${clockTime(live.until)}` : "until the scene is released";
  return el("p", {
    class: "note wall-scene",
    text: `A scene shows ${entry.title || "a work"} here ${until}. Skip moves the schedule beneath it, and the wall shows that when the scene ends.`,
  });
}

/* The server's sentence about how much of the theme reached the wall. Marked
 * as a problem when none of it did, because the wall is then dark although a
 * theme hangs there; the sentence says so ("so the wall is dark"), and the
 * glyph only draws the eye to it. */
function summaryLine(manifest) {
  if (manifest.entries.length > 0) return el("p", { class: "note", text: manifest.summary });
  return el("p", { class: "note wall-feed wall-dark" }, [el("span", { text: `${GLYPHS.problem} ${manifest.summary}` })]);
}

/* A screen not showing art, in the product's voice. `showing_art` and `silent`
 * are worded where the card is built, because they lead with a work or with
 * when the wall was last heard from. */
const STATE_WORDS = {
  in_use: "Somebody is using the screen",
  dark: "Its screen is off",
  no_screen: "No screen",
  // Not drawn in a lead (the badge and the problem line say it), and held here
  // because every state the server sends has its words.
  unassigned: "No Player",
  unreachable: "Not known",
};

/* What a state says about the screen, for one the card names in words. A state
 * this client has no words for is said to be not known, never read as another. */
function stateWords(state) {
  return STATE_WORDS[state] || STATE_WORDS.unreachable;
}

/* The lead for a wall that names no work: the state, and since when, then the
 * work it showed last, large, where the server has one. */
function stateLead(wall, shown, said, silent, last, first) {
  if (!silent && said.state === "dark") return darkLead(wall, shown, last, first);
  const words = said.state === "showing_art" ? `A picture ${wall.name} did not put there` : stateWords(said.state);
  const lines = silent
    ? [el("p", { class: "wall-now-when", text: lastHeard(shown) }), el("p", { class: "muted", text: `When it last reported: ${words}.` })]
    : said.state === "showing_art"
      ? [el("p", { class: "wall-now-when", text: "On the wall now" }), el("p", { class: "wall-now-state", text: words })]
      : [
          el("p", { class: "wall-now-state", text: words }),
          // A Player before display state has a work or nothing to say. One
          // that reports state and says unreachable cannot tell what its screen
          // shows; the server also reads a state it has no name for as
          // unreachable, so the sentence must be true of both.
          said.state === "unreachable"
            ? el("p", {
                class: "muted",
                text: shown.since
                  ? `${wall.name}'s display is reporting, and cannot say what its screen is showing.`
                  : `${wall.name}'s display is reporting, and has not said which work it is showing.`,
              })
            : null,
          shown.since ? el("p", { class: "muted", text: `Since ${readable(shown.since)}` }) : null,
        ];
  return el("div", { class: "wall-now", "data-state": shown.state }, [...lines, last ? lastShownFigure(wall, last) : null]);
}

/* A dark screen: the work it showed last, dimmed, or, while the wall has shown
 * nothing the server logged, the work that comes on when the screen does (ruling
 * 6 of 2026-10-27, which keeps ruling 3 of 2026-10-11 and falls back for an
 * empty log). Under one line saying since when the screen has been off. */
function darkLead(wall, shown, last, first) {
  // "Screen off" is the badge's, at the card's head; this line says since when,
  // so the card says the screen is off once.
  const since = shown.since ? `Off since ${readable(shown.since)}` : "Off";
  let figure = null;
  if (last) figure = lastShownFigure(wall, last);
  else if (first) figure = workFigure(wall, first.work, `Next, when the screen comes on, from ${readable(first.slot.starts_at)}`, "wall-last");
  return el("div", { class: "wall-now wall-dim", "data-state": shown.state }, [el("p", { class: "wall-now-state", text: since }), figure]);
}

/* The work the wall showed last, as large as the work on it would be, under
 * how long it was up: until it ended, or for a wall that went quiet while
 * showing it, until it was last seen. */
function lastShownFigure(wall, last) {
  const { showing } = last;
  const when = showing.ended ? `Last on the wall, until ${readable(showing.until)}` : `Last seen on the wall ${readable(showing.until)}`;
  if (!last.work) {
    return el("div", { class: "wall-last" }, [
      el("p", { class: "wall-now-when", text: when }),
      el("p", { class: "note", text: `${wall.name} last showed a work that could not be read — ${last.failure}.` }),
    ]);
  }
  return workFigure(wall, last.work, when, "wall-last");
}

/* When the wall was last heard from, from the server's own age of the report. */
function lastHeard(shown) {
  return `Not heard from since ${readable(shown.reported_at)} (${ago(shown.age_seconds)})`;
}

/* The card's lead: what the wall's screen is doing.
 *
 * Showing art: the work, large, with its label, under "On the wall now"; a
 * picture this wall did not put there (a remote-control change the wall could
 * not match to a work) is said to be one. Silent: when it was last heard from,
 * and the work it last reported, which is still the best answer to what is on
 * the wall but not a claim about this minute. Anything else: the state in words.
 * A wall that has never readably reported leads with nothing, because reason
 * three below says so with the way to its reading.
 *
 * The image carries the work and its artist in its `alt`, because here the image
 * is the content rather than a thumbnail beside it. The title is the link to the
 * work's page, so the card has one tab stop for the work rather than two. */
function nowShowing(wall, now) {
  const shown = now ? now.shown : null;
  if (!shown || (shown.state === "silent" && !shown.last)) {
    // Nothing readable to say about the screen; what it showed last still leads.
    if (now && now.last) return el("div", { class: "wall-now" }, [lastShownFigure(wall, now.last)]);
    return el("div", { class: "wall-now", hidden: true });
  }
  const silent = shown.state === "silent";
  const said = silent ? shown.last : shown;
  // No Player: the badge says so and the line under it has the way to fix it,
  // so the lead adds nothing (a state is worded once, 2026-10-27).
  if (!silent && said.state === "unassigned") return el("div", { class: "wall-now", "data-state": "unassigned", hidden: true });
  if (!now.workId) return stateLead(wall, shown, said, silent, now.last, ledWith(now));
  const when = silent ? `${lastHeard(shown)}, so this may have changed since` : "On the wall now";
  if (now.failure) {
    return el("div", { class: "wall-now" }, [
      el("p", { class: "wall-now-when", text: when }),
      el("p", { class: "note", text: `${wall.name} reports showing a work that could not be read — ${now.failure}.` }),
    ]);
  }
  return workFigure(wall, now.work, when, "wall-now");
}

/* A work drawn large with its label: the work on the wall now, or the one it
 * showed last. */
function workFigure(wall, work, when, kind) {
  const artist = work.artist ? work.artist.name : null;
  const image = el("img", {
    // The large size: this box is drawn up to 48rem wide, and the tile's 480 px
    // is soft there on a 2x screen. The bare work: the mat is the wall's.
    src: `/api/works/${encodeURIComponent(work.artwork_id)}/thumbnail?size=large`,
    alt: artist ? `${work.title}, ${artist}` : work.title,
  });
  // A file can go away between the heartbeat and this fetch. Without this the
  // lead renders as a blank box — silent, which is the failure mode this whole
  // product exists to refuse.
  image.addEventListener("error", () => {
    image.replaceWith(absentImage("Its image could not be loaded just now."));
  });
  return el("figure", { class: kind }, [
    el("p", { class: "wall-now-when", text: when }),
    el("div", { class: "wall-now-picture" }, [image]),
    el("figcaption", { class: "wall-now-label" }, [
      el("h3", { class: "wall-now-title" }, [link({ view: "work", id: work.artwork_id }, { text: work.title })]),
      el("p", { class: "wall-now-artist", text: artist || "Artist unrecorded" }),
      work.date_created || work.medium
        ? el("p", { class: "muted wall-now-facts", text: [work.date_created, work.medium].filter(Boolean).join(" · ") })
        : null,
      // Programming's judgement against the screen this wall's Player reports
      // (`programming/adequacy.py`). Said, never hidden: a postage stamp in a
      // big mat looks like a fault, and the reason is the picture's size.
      (wall.too_small || []).includes(work.artwork_id)
        ? el("p", { class: "note wall-now-small", text: `Too small for ${wall.name}: it fills less than half of the space inside the mat. A larger scan would fix it.` })
        : null,
    ]),
  ]);
}

/* The upcoming work a dark wall with nothing logged leads with (`darkLead`), or
 * null. Decided here once, for the lead and for the row under it: the row skips
 * exactly the work the lead drew, and a first work that could not be read leads
 * nothing and stays in the row with its failure. */
function ledWith(now) {
  if (!now || !now.shown || now.shown.state !== "dark" || now.workId || now.last) return null;
  const first = now.next.length ? now.next[0] : null;
  return first && first.work ? first : null;
}

/* The next three works the wall's schedule puts up, each small, with when it
 * goes up. Nothing while the wall has no feed: there is nothing coming. */
function nextUp(wall, now) {
  // So the row starts at the second rather than drawing the lead's work twice.
  const led = Boolean(ledWith(now));
  const next = now ? now.next.slice(led ? 1 : 0) : [];
  if (!next.length) return el("div", { class: "wall-next", hidden: true });
  return el("div", { class: "wall-next" }, [
    el("h3", { class: "wall-next-title", text: led ? "Then" : "Up next" }),
    el(
      "ol",
      { class: "wall-next-list" },
      next.map(({ slot, work, failure }) =>
        el("li", {}, [
          work
            ? el("img", {
                src: `/api/works/${encodeURIComponent(work.artwork_id)}/thumbnail`,
                alt: "",
                loading: "lazy",
              })
            : null,
          el("span", { class: "wall-next-work" }, [
            work ? link({ view: "work", id: work.artwork_id }, { text: work.title }) : el("span", { text: `A work that could not be read — ${failure}` }),
            el("span", { class: "muted wall-next-when", text: `From ${readable(slot.starts_at)}` }),
          ]),
        ]),
      ),
    ),
  ]);
}

/* The four reasons, dispatched. Each is its own function below, and that is not
 * decoration: they are four branches with four texts and four fixes, and a
 * dispatch that fell through to a shared sentence would be the single "nothing is
 * showing" this screen exists not to say. */
function emptiness(reason, wall, build, beats, themes) {
  if (reason === "no-theme") return noThemeHung(wall, themes);
  if (reason === "empty-theme") return emptyTheme(wall, build.manifest);
  if (reason === "silent") return planeSilent(wall, beats.byWall.get(wall.wall_id));
  if (reason === "unreachable") return unreachable(cannotReach(wall, build, beats));
  return [];
}

/* Reason one: no theme has been hung here.
 *
 * The fix is the Hanging picker in this wall's own card, a few lines below,
 * so the sentence points at it rather than
 * sending the curator to another screen for the one act this screen is named for. */
function noThemeHung(wall, themes) {
  // Pointing at the picker only when it is there: with no theme to choose, the
  // Hanging line below says so and offers to create one.
  return [
    el("p", {
      class: "muted",
      text: themes.length ? `Nothing is hanging on ${wall.name}. Choose a theme under Hanging, below.` : `Nothing is hanging on ${wall.name}.`,
    }),
  ];
}

/* Reason two: a theme is hung and holds no works.
 *
 * A different state from "the theme's works were all excluded", and the fix is
 * different too: there is nothing to exclude, and nothing to diagnose. */
function emptyTheme(wall, manifest) {
  return [
    el("p", {
      class: "note",
      text: `${manifest.theme.name} holds no works yet, so nothing is on ${wall.name}.`,
    }),
    el("div", { class: "row" }, [
      // The theme's own address, not the index. `information-architecture.md`
      // § Screen Inventory lists "a wall's theme control" as an entry point to
      // the Theme screen, and a link naming one theme that lands on a list of
      // all of them makes the curator find it again — on the one screen whose
      // sentence directly above says which theme is the problem.
      link({ view: "theme", id: manifest.theme.theme_id }, { class: "action quiet", text: `Add works to ${manifest.theme.name}` }),
    ]),
  ];
}

/* Reason three: this plane published, and no display has said anything back.
 *
 * **A reading that arrived**, which is what separates this from reason four: the
 * curation plane answered, and what it answered with is that the display plane
 * has not spoken. Both an absent heartbeat and one that cannot be read land here
 * — a corrupt report is still the display plane failing to speak, the wall is
 * equally dark either way, and the fix is the same: go and read the observation
 * in full. What differs is the sentence, because "nothing has ever been written"
 * and "something was written and cannot be parsed" send an operator to different
 * places on the appliance. */
function planeSilent(wall, beat) {
  return [
    el("p", { class: "note", text: silence(wall, beat) }),
    el("div", { class: "row" }, [
      link({ view: "health" }, { class: "action quiet", text: `Open the reading for ${wall.name}` }),
    ]),
  ];
}

function silence(wall, beat) {
  if (!beat) {
    return `The health reading carries no heartbeat for ${wall.name}, so nothing here can say whether a display is serving it.`;
  }
  if (beat.problem) {
    return `${wall.name}'s heartbeat cannot be read: ${beat.problem}. What is published is what a display would pick up, and nothing confirms one has.`;
  }
  return `No display has ever reported for ${wall.name}. What is published is waiting to be picked up; until something reports, nothing here can say the wall is showing it.`;
}

/* Reason four: a plane could not be reached, and the sentence says which one did
 * answer.
 *
 * The only fix that can be offered is to ask again, and it is offered rather than
 * left to the curator to work out that reloading is a thing they may do. A link
 * to the health screen would be worse than nothing here: the reading it shows is
 * the one that could not be fetched. */
function unreachable(words) {
  return [
    el("p", { class: "note", text: words }),
    el("div", { class: "row" }, [
      el("button", {
        class: "action quiet",
        type: "button",
        text: "Ask again",
        // No argument, so the repaint does not move focus. See the file header.
        onclick: () => guard(() => refresh()),
      }),
    ]),
  ];
}

function cannotReach(wall, build, beats) {
  if (build.failure) {
    return `The curation plane answered for the walls and refused ${wall.name}'s build — ${build.failure} — so nothing here can say what is on this wall. The display plane was not asked.`;
  }
  return `The curation plane answered for ${wall.name}, and the reading that speaks for the display plane did not — ${beats.failure} — so nothing here can say whether anything is on the wall.`;
}

/* Skip and Remove…: the card's acts, under the work they act on.
 *
 * **No take-down control here, deliberately.** Taking down lives on the theme,
 * where it exists to make a theme deletable. It would also read wrong here: a
 * take-down rewrites no manifest, so pressing it on the screen whose whole job is
 * to say what is on the wall would leave the card reading "nothing is hanging"
 * while the television went on showing the pictures. Hanging another theme is
 * the act on this screen that actually changes the wall (`hangingFacts`). */
function acts(card, reason, manifest) {
  const { wall } = card;
  // Only where something is actually up. A wall showing nothing has no
  // schedule to move on through (the server refuses the step), and offering it
  // would say this screen thinks there is something to move on from.
  //
  // **Both halves are load-bearing.** The reason answers whether a display has
  // spoken for this wall; the manifest answers whether there is anything for a
  // step to advance through. A theme whose works were *all* excluded is not one
  // of the four reasons — `considered` counts entries plus exclusions, so it
  // reads as hanging — and it published an empty rotation.
  const live = reason === "hanging" && manifest.entries.length > 0;
  // Only with a work to name: the display state's, which is the one a person in
  // the room is tired of. A wall that has not said what it shows has nothing
  // for this to be about.
  const removable = Boolean(card.now && card.now.workId && wall.theme);
  if (!live && !removable) return null;
  return el("div", { class: "row wall-acts" }, [live ? skipButton(card) : null, removable ? removeButton(card) : null]);
}

/* Skip: the next work in this wall's rotation, and only this wall's.
 *
 * **Unconfirmed, and that is a decision rather than an oversight.** Flow 6 names
 * activation as the one act that gets a confirmation, and it is the one that
 * replaces everything on a wall. A skip advances by one work in a rotation that
 * was going to advance by itself anyway. A dialog in front of it would teach the
 * curator to dismiss dialogs.
 *
 * The wall changes when its Player next reads its feed, and the card can
 * only know which work came up when the heartbeat reports it, so it says so and
 * watches for that (`awaitNext`). */
function skipButton(card) {
  const { wall } = card;
  return el("button", {
    class: "action",
    type: "button",
    text: "Skip",
    "aria-label": `Skip the work on ${wall.name}`,
    onclick: (event) =>
      attempt(
        event.currentTarget,
        `skip the work on ${wall.name}`,
        () => api(`/api/walls/${encodeURIComponent(wall.wall_id)}/next`, { method: "POST" }),
        { then: () => awaitNext(card, `Skipped. ${wall.name} shows its next work when its display next reports, usually within a minute.`) },
      ),
  });
}

/* *Remove…* (it was *Not this one again*: ruling 2 of 2026-10-27), and the one
 * question it asks: from this theme, or from every wall. Two different changes
 * (S8 says "nothing else changed"), so the curator says which; neither is
 * Archive, which would take the work out of the library. The question is a
 * dialog whose two answers are the act, so there is nothing further to confirm. */
function removeButton(card) {
  const { wall } = card;
  return el("button", {
    class: "action quiet",
    type: "button",
    text: "Remove…",
    "aria-haspopup": "dialog",
    "aria-label": `Remove the work on ${wall.name}…`,
    onclick: () => askWhere(card),
  });
}

/* The two answers, built when the question is opened so they name the work the
 * card leads with then, which a Skip may have changed since the card was drawn. */
function askWhere(card) {
  const { wall } = card;
  const title = card.now.work ? card.now.work.title : "this work";
  const from = wall.theme.hidden ? "this selection" : wall.theme.name;
  let panel = null;
  const answer = (scope, text, sub, act) =>
    el("button", {
      class: "action quiet remove-choice",
      type: "button",
      "aria-label": `${text}: ${sub}`,
      onclick: (event) =>
        attempt(
          event.currentTarget,
          act,
          () =>
            api(`/api/walls/${encodeURIComponent(wall.wall_id)}/not-again`, {
              method: "POST",
              body: JSON.stringify({ artwork_id: card.now.workId, scope }),
            }),
          {
            then: () => {
              panel.close();
              return awaitNext(card, removedSaid(wall, title, scope, from), scope === "every_wall" ? card.now.workId : null);
            },
          },
        ),
    }, [el("span", { class: "remove-choice-what", text }), el("span", { class: "muted remove-choice-sub", text: sub })]);
  panel = openPanel({
    title: `Remove ${title} from ${wall.name}`,
    closeLabel: "Cancel",
    body: [
      answer("theme", `Take it out of ${from}`, "It stays in your library and in your other themes.", `take ${title} out of ${from}`),
      answer("every_wall", "Keep it off every wall", "It stays in your library and its themes, and no wall shows it.", `keep ${title} off every wall`),
    ],
  });
}

function removedSaid(wall, title, scope, from) {
  const done =
    scope === "every_wall"
      ? `${title} is kept off every wall. It stays in the library and in its themes.`
      : `${title} is out of ${from}. Nothing else changed.`;
  return `${done} ${wall.name} shows its next work when its display next reports.`;
}

/* *Hanging*: what the wall hangs, as the control that hangs another (ruling 3
 * of 2026-10-27: a fact that can be changed is its own control, and no words
 * say that it could be), and how the wall plays it.
 *
 * **A picker rather than a button per theme**, the opposite of the choice
 * `screens/theme.js` makes for walls, and for the reason stated there: a button
 * per target suits a small set, and the themes are the side that grows. Its
 * accessible name carries the wall's, so a reader moving by form field knows
 * which room it belongs to. Choosing a theme asks first (`core/hanging.js`, the
 * one wording of hanging), and a declined question puts the picker back.
 * Selections are not offered: the server leaves them out of the list, so a wall
 * hanging one shows it as the picker's first, unchoosable entry. */
function hangingFacts(wall, themes, manifest) {
  if (!themes.length) {
    // Nothing to choose, so no picker: a control with no choice in it is a dead
    // end. A wall hanging a selection still says so.
    return el("div", { class: "row wall-hanging wall-controls" }, [
      wall.theme
        ? el("p", { text: "Hanging a selection. No theme has been created to hang instead." })
        : el("p", { class: "muted", text: "No theme has been created yet, so there is nothing to hang here." }),
      link({ view: "theme" }, { class: "action", text: "Create a theme" }),
    ]);
  }
  const pickerId = `hang-${wall.wall_id}`;
  const current = wall.theme && !wall.theme.hidden ? wall.theme.theme_id : "";
  const picker = el("select", { id: pickerId, class: "fact-picker" }, [
    !wall.theme ? el("option", { value: "", text: "Nothing — choose a theme", disabled: true, selected: true }) : null,
    wall.theme && wall.theme.hidden ? el("option", { value: "", text: "A selection", disabled: true, selected: true }) : null,
    ...themes.map((placement) => el("option", { value: placement.theme.theme_id, text: placement.theme.name, selected: placement.theme.theme_id === current })),
  ]);
  picker.addEventListener("change", async () => {
    const chosen = themes.find((placement) => placement.theme.theme_id === picker.value);
    const hung = await hangTheme({ control: picker, themeId: chosen.theme.theme_id, themeName: chosen.theme.name, wall, then: refresh });
    if (!hung) picker.value = current;
  });
  // `wall-controls`: the card's one control every card has, which is what a
  // test (and a reader) waits for to know the card is drawn.
  return el("dl", { class: "facts wall-hanging wall-controls" }, [
    // The visible term is the word; the field's own label names the wall too.
    el("dt", { "aria-hidden": "true", text: "Hanging" }),
    el("dd", {}, [el("label", { for: pickerId, class: "visually-hidden", text: `Hanging on ${wall.name}` }), picker]),
    manifest ? el("dt", { text: "Changes" }) : null,
    manifest ? el("dd", { text: playsWords(manifest) }) : null,
  ]);
}

/* How the wall plays what hangs on it, in one line: the interval and the order,
 * the default resolved by the server (`GET /api/manifest`). */
function playsWords(manifest) {
  return `every ${durationWords(manifest.rotation_interval_seconds)}, ${manifest.shuffle ? "shuffled" : "in the theme's order"}`;
}

/* The card's foot: the places this wall's account continues. History is a link
 * because it goes to another page; the works this wall cannot show are a list too
 * long for the card, so they open in a panel, and the line is there only when
 * there are any (an exception stays quiet until it blocks). */
function footer(wall, manifest) {
  const kept = manifest ? manifest.exclusions : [];
  if (!wall.theme && !kept.length) return null;
  return el("footer", { class: "wall-foot" }, [
    wall.theme ? link({ view: "history", params: { wall: wall.wall_id } }, { class: "wall-history", text: "History", "aria-label": `History of ${wall.name}` }) : null,
    kept.length
      ? el("button", {
          class: "action quiet wall-kept",
          type: "button",
          "aria-haspopup": "dialog",
          text: `${counted(kept.length, "work")} can't be shown here…`,
          "aria-label": `${counted(kept.length, "work")} can't be shown on ${wall.name}: see which and why`,
          onclick: () =>
            openPanel({
              title: `Not on ${wall.name}`,
              lead: "Every work this wall draws from that is not on it, and why.",
              body: [
                table(
                  "Every work this wall draws from that is not on it, and exactly why.",
                  ["Title", "Reason", "What is missing"],
                  kept.map((x) => [x.title, EXCLUSION_WORDS[x.reason] || x.reason, x.detail]),
                ),
              ],
            }),
        })
      : null,
  ]);
}

/* After a Skip or *Remove…*: say what happens next, then watch this
 * wall's display state until it names a different work, and lead the card with it.
 *
 * `gone` is a work that must not be taken for the new one even if the wall
 * names it again (a report written before the Player read the change).
 *
 * Bounded twice: by `STALE_AFTER_SECONDS`, past which a heartbeat that has not
 * moved is a display that has stopped, and by leaving the screen (`state.poll`
 * moves on every navigation, as the run view's chain reads it). Only the lead and
 * the next three are replaced, so focus stays where the curator left it. A walls read that fails
 * mid-watch is not the act failing; the watch stops and says so. */
async function awaitNext(card, sentence, gone = null) {
  const { wall } = card;
  const generation = state.poll;
  const before = card.now ? card.now.workId : null;
  card.said.textContent = sentence;
  const deadline = Date.now() + STALE_AFTER_SECONDS * 1000;
  while (Date.now() < deadline) {
    await new Promise((resolve) => setTimeout(resolve, WATCH_MS));
    if (state.poll !== generation || !card.said.isConnected) return;
    let current;
    try {
      current = (await api("/api/walls")).walls.find((each) => each.wall_id === wall.wall_id);
    } catch (failure) {
      card.said.textContent = `${sentence} This page could not read what ${wall.name} is showing — ${failure.message}.`;
      return;
    }
    const next = current ? shownWork(current.display_state) : null;
    if (!next || next === before || next === gone) continue;
    const now = await nowOn(current);
    if (state.poll !== generation || !card.said.isConnected) return;
    const lead = nowShowing(wall, now);
    card.lead.replaceWith(lead);
    card.lead = lead;
    const coming = nextUp(wall, now);
    card.next.replaceWith(coming);
    card.next = coming;
    card.now = now;
    card.said.textContent = now.work ? `${wall.name} now shows ${now.work.title}.` : `${wall.name} now shows another work.`;
    return;
  }
  card.said.textContent = `${sentence} It has not reported a new work in ${inWords(STALE_AFTER_SECONDS)}; Status has its reading.`;
}

/* Why a work in the theme is not on the wall, as a word, by the server's
 * `UnplayableReason` and `KeptOff`. Held to both enums by the vocabulary test;
 * one it has no word for is shown as itself. The *What is missing* column
 * beside it carries the server's own sentence. */
const EXCLUSION_WORDS = {
  archived: "Archived",
  no_original: "No image yet",
  no_rendition: "Not prepared yet",
  stale_rendition: "Being prepared again",
  no_mat_color: "No mat colour",
  not_in_catalogue: "No longer in the library",
  kept_off_every_wall: "Kept off every wall",
  outside_wall_shape: "Outside this wall's shapes",
};

/* *Edit…*: the wall's settings in one dialog (ruling 4 of 2026-10-27): its name,
 * where it shows (the Player and screen, and its label panels), how it rotates,
 * which shapes it shows, and its mat. Each part is set by its own act and says so
 * in place, as the panels always have, so a change made in one part is never held
 * hostage by another. The card is repainted when the dialog closes after any part
 * changed something: the name, the Player and the labels close it at once, since
 * the card is where they show; the rotation, shapes and mat leave it open to go
 * on working in, and the card's *Changes*, next works and what it cannot show
 * catch up on the way out. */
function editWall(wall, manifest, shownBy) {
  const edit = editing();
  edit.panel = openPanel({
    title: `Edit ${wall.name}`,
    body: [
      nameSection(wall, edit.done),
      whereSection(wall, shownBy, edit.done),
      labelsSection(wall, shownBy, edit.done),
      ...(manifest ? playbackPanels(wall, manifest, edit.changed) : []),
      manifest ? matPanel(wall, edit.changed) : null,
    ],
    onClose: edit.closed,
  });
}

/* What a dialog that changes walls needs: `changed` when an act lands, `done`
 * when it lands and the dialog has nothing more to do, and `closed` for
 * `openPanel`'s `onClose`, which repaints the page if anything changed. A dialog
 * left by a link repaints nothing here: the page it went to paints itself. The
 * dialog is closed by its own handle, so this never closes a panel it did not
 * open. */
function editing() {
  const edit = { panel: null, wrote: false };
  edit.changed = () => (edit.wrote = true);
  edit.done = () => {
    edit.changed();
    edit.panel.close();
  };
  edit.closed = () => {
    if (edit.wrote && state.view === "walls") refresh();
  };
  return edit;
}

/* The wall's name. The server refuses an empty one or one another wall has, in
 * words this dialog shows beside the field. */
function nameSection(wall, done) {
  const nameId = `wall-name-${wall.wall_id}`;
  const field = el("input", { id: nameId, type: "text", value: wall.name });
  return el("div", { class: "panel" }, [
    el("h3", { text: "Name" }),
    el("div", { class: "row" }, [
      el("div", { class: "field" }, [el("label", { for: nameId, text: "Name" }), field]),
      el("button", {
        class: "action",
        type: "button",
        text: "Rename",
        "aria-label": `Rename ${wall.name}`,
        onclick: (event) =>
          attempt(
            event.currentTarget,
            `rename ${wall.name}`,
            () => api(`/api/walls/${encodeURIComponent(wall.wall_id)}`, { method: "POST", body: JSON.stringify({ name: field.value }) }),
            { then: done },
          ),
      }),
    ]),
  ]);
}

/* The screens a client reported, by name, with whether something is connected:
 * what the Player picker's screen choice offers. */
function screensOf(client) {
  const outputs = client && client.heartbeat && Array.isArray(client.heartbeat.outputs) ? client.heartbeat.outputs : [];
  return outputs.filter((output) => output.kind !== "epd");
}

/* Which Player shows the wall, and on which screen: the line that says what the
 * Player last reported about it, then the two pickers and *Show it there*. None
 * takes the wall off its Player; its theme stays hung. */
function whereSection(wall, shownBy, done) {
  const clients = shownBy.byId ? [...shownBy.byId.values()] : [];
  const playerId = `wall-player-${wall.wall_id}`;
  const screenId = `wall-screen-${wall.wall_id}`;
  const player = el("select", { id: playerId }, [
    el("option", { value: "", text: "None", selected: !wall.client_id }),
    ...clients.map((client) => el("option", { value: client.client_id, text: client.name, selected: client.client_id === wall.client_id })),
  ]);
  const screen = el("select", { id: screenId });
  const fillScreens = () => {
    const client = shownBy.byId ? shownBy.byId.get(player.value) : null;
    const screens = screensOf(client);
    fill(
      screen,
      ...(screens.length
        ? screens.map((output) =>
            el("option", {
              value: output.name,
              text: `${screenName(output.name)}${output.connected ? "" : " · nothing connected"}`,
              selected: client && client.client_id === wall.client_id && output.name === wall.output,
            }),
          )
        : [el("option", { value: "", text: client ? "It has not reported its screens" : "—", disabled: true, selected: true })]),
    );
    screen.disabled = !client || !screens.length;
  };
  player.addEventListener("change", fillScreens);
  fillScreens();
  return el("div", { class: "panel" }, [
    el("h3", { text: "Where it shows" }),
    assignmentLine(wall, shownBy),
    shownBy.failure ? el("p", { class: "note", text: `The Players could not be read — ${shownBy.failure}.` }) : null,
    el("div", { class: "row" }, [
      el("div", { class: "field" }, [el("label", { for: playerId, text: `Player for ${wall.name}` }), player]),
      el("div", { class: "field" }, [el("label", { for: screenId, text: "Screen" }), screen]),
      el("button", {
        class: "action",
        type: "button",
        text: "Show it there",
        "aria-label": `Show ${wall.name} there`,
        onclick: (event) =>
          attempt(
            event.currentTarget,
            player.value ? `show ${wall.name} on that screen` : `take ${wall.name} off its Player`,
            () =>
              player.value
                ? api(`/api/walls/${encodeURIComponent(wall.wall_id)}/client`, {
                    method: "POST",
                    body: JSON.stringify({ client_id: player.value, output: screen.value }),
                  })
                : api(`/api/walls/${encodeURIComponent(wall.wall_id)}/client`, { method: "DELETE" }),
            { then: done },
          ),
      }),
    ]),
  ]);
}

/* The label panels captioning the wall, each with *Stop captioning*, then one to
 * add from those the Players reported that caption no wall: the server refuses a
 * panel captioning another wall until it is taken off that one, so offering it
 * would offer a choice that cannot succeed. */
function labelsSection(wall, shownBy, done) {
  const clients = shownBy.byId ? [...shownBy.byId.values()] : [];
  const offered = clients.flatMap((client) =>
    (client.label_outputs || []).filter((label) => label.wall_id == null).map((label) => ({ client, output: label.output })),
  );
  const pickId = `wall-label-${wall.wall_id}`;
  const pick = el(
    "select",
    { id: pickId },
    offered.map(({ client, output }, at) => el("option", { value: String(at), text: panelName(output, client) })),
  );
  const ownerOf = (label) => (shownBy.byId ? shownBy.byId.get(label.client_id) : null);
  return el("div", { class: "panel" }, [
    el("h3", { text: "Label panel" }),
    labelsLine(wall),
    ...(wall.labels || []).map((label) =>
      el("div", { class: "row" }, [
        el("span", { text: panelName(label.output, ownerOf(label), label.client_name) }),
        el("button", {
          class: "action quiet",
          type: "button",
          text: "Stop captioning",
          "aria-label": `Stop ${panelName(label.output, ownerOf(label), label.client_name)} captioning ${wall.name}`,
          onclick: (event) =>
            attempt(
              event.currentTarget,
              `stop ${panelName(label.output, ownerOf(label), label.client_name)} captioning ${wall.name}`,
              () => api(`/api/walls/${encodeURIComponent(wall.wall_id)}/labels/${encodeURIComponent(label.label_id)}`, { method: "DELETE" }),
              { then: done },
            ),
        }),
      ]),
    ),
    offered.length
      ? el("div", { class: "row" }, [
          el("div", { class: "field" }, [el("label", { for: pickId, text: `Caption ${wall.name} with` }), pick]),
          el("button", {
            class: "action",
            type: "button",
            text: "Caption it",
            "aria-label": `Caption ${wall.name} with this label panel`,
            onclick: (event) => {
              const { client, output } = offered[Number(pick.value)];
              return attempt(
                event.currentTarget,
                `caption ${wall.name} with ${panelName(output, client)}`,
                () =>
                  api(`/api/walls/${encodeURIComponent(wall.wall_id)}/labels`, {
                    method: "POST",
                    body: JSON.stringify({ client_id: client.client_id, output }),
                  }),
                { then: done },
              );
            },
          }),
        ])
      : wall.labels && wall.labels.length
        ? null
        : el("p", { class: "muted", text: "No Player has reported a label panel." }),
  ]);
}

/* A label panel in the words a person reads (`information-architecture.md`
 * § Vocabulary): *the label panel on Hall Pi*. Its port is named only when that
 * Player has more than one, since then it is the one thing telling them apart.
 * `clientName` stands in when the Player itself could not be read. */
function panelName(output, client, clientName = null) {
  const name = client ? client.name : clientName || "a Player whose name could not be read";
  const several = Boolean(client && (client.label_outputs || []).length > 1);
  return several ? `label panel ${output} on ${name}` : `the label panel on ${name}`;
}

/* *Add wall…*: its name. Its Player is chosen with the new card's *Edit…*, and a
 * theme hung from its Hanging picker, which asks first as every hang does. */
function addWallOpener() {
  return el("button", {
    class: "action quiet",
    type: "button",
    text: "Add wall…",
    "aria-haspopup": "dialog",
    onclick: () => {
      const nameId = "new-wall-name";
      const name = el("input", { id: nameId, type: "text", placeholder: "Hall" });
      const edit = editing();
      const add = el("button", {
        class: "action",
        type: "button",
        text: "Add wall",
        onclick: (event) =>
          attempt(
            event.currentTarget,
            `add the wall ${name.value.trim() || "with no name"}`,
            () => api("/api/walls", { method: "POST", body: JSON.stringify({ name: name.value }) }),
            { then: edit.done },
          ),
      });
      edit.panel = openPanel({
        title: "Add a wall",
        lead: "A wall is a place that shows art. Once it is added, choose its Player with Edit… and what it hangs with Hanging, on its card.",
        closeLabel: "Cancel",
        body: [el("div", { class: "field" }, [el("label", { for: nameId, text: "Name" }), name])],
        actions: [add],
        onClose: edit.closed,
      });
    },
  });
}

/* The rotation and shapes panels, which share one route
 * (`PUT /api/walls/{id}/playback`). Each sends only its own fields, and the
 * server leaves the rest as they are: a body carrying the other panel's
 * settings as this page first drew them would put back whatever was set since,
 * here or on another surface. */
function playbackPanels(wall, manifest, changed) {
  const send = (changes) =>
    api(`/api/walls/${encodeURIComponent(wall.wall_id)}/playback`, { method: "PUT", body: JSON.stringify(changes) });
  return [rotationPanel(wall, manifest, send, changed), shapesPanel(wall, send, changed)];
}

/* The wall's orders in the curator's words, in the order the picker offers
 * them: the value sent (`shuffle`), and the picker's words. The empty value is
 * no choice at all: the deployment's default, which the facts below resolve. */
const ORDER_CHOICES = [
  ["", "Default"],
  ["false", "As curated"],
  ["true", "Shuffled"],
];

/* How the wall plays what hangs on it: how long each work stays up, and whether
 * in the theme's order or shuffled. The wall's settings, not the theme's
 * (ruling 2 of 2026-10-11), so they stay when another theme is hung.
 *
 * Minutes here and seconds on the wire: a curator thinks of a work staying up
 * for minutes, and a decimal still reaches a 90-second interval. Empty is the
 * default. The facts say what the wall plays at now, the default resolved, and
 * are asked of the server again (`GET /api/manifest`) after Set rather than worked out here,
 * since only the server knows the default. */
function rotationPanel(wall, manifest, send, changed) {
  const intervalId = `interval-${wall.wall_id}`;
  const orderId = `order-${wall.wall_id}`;
  const interval = el("input", {
    id: intervalId,
    type: "number",
    step: "any",
    inputmode: "decimal",
    placeholder: "Default",
    // To two places, so 931 seconds reads 15.52 rather than 15.516666666666667;
    // sent back unchanged it rounds to the same whole second.
    value: wall.rotation_interval_seconds == null ? "" : String(Math.round((wall.rotation_interval_seconds / 60) * 100) / 100),
  });
  const order = el("select", { id: orderId });
  for (const [value, words] of ORDER_CHOICES) {
    order.append(el("option", { value, text: words, selected: String(wall.shuffle ?? "") === value }));
  }
  const now = el("div", {}, [rotationFacts(manifest)]);
  // Said here and the dialog left open, as the mat's is; the card catches up
  // when it closes (`editWall`).
  const said = el("p", { class: "wall-said", role: "status" });
  return el("div", { class: "panel" }, [
    el("h3", { text: "How it rotates" }),
    now,
    el("div", { class: "row" }, [
      el("div", { class: "field" }, [el("label", { for: intervalId, text: `Minutes each work stays up on ${wall.name}` }), interval]),
      el("div", { class: "field" }, [el("label", { for: orderId, text: `Order on ${wall.name}` }), order]),
      el("button", {
        class: "action",
        type: "button",
        text: "Set the rotation",
        "aria-label": `Set the rotation on ${wall.name}`,
        onclick: (event) => {
          // A number field holding something that is not a number reads as
          // empty, which would quietly mean "the default": asked apart.
          if (interval.validity.badInput) {
            said.textContent = "Minutes must be a number, or left empty for the default.";
            return;
          }
          const minutes = interval.value.trim() === "" ? null : Number(interval.value);
          // Refused here only what the server would refuse anyway, so the
          // sentence names the field rather than the route.
          if (minutes !== null && !(minutes > 0)) {
            said.textContent = "Minutes must be more than zero, or left empty for the default.";
            return;
          }
          return attempt(
            event.currentTarget,
            `set the rotation on ${wall.name}`,
            () =>
              send({
                // A second at least: the wire is whole seconds, and the server refuses zero.
                rotation_interval_seconds: minutes === null ? null : Math.max(1, Math.round(minutes * 60)),
                shuffle: order.value === "" ? null : order.value === "true",
              }),
            {
              then: async () => {
                changed();
                const fresh = await api(`/api/manifest?wall_id=${encodeURIComponent(wall.wall_id)}`);
                fill(now, rotationFacts(fresh));
                said.textContent = `Rotation on ${wall.name}: ${rotationWords(fresh)}.`;
              },
            },
          );
        },
      }),
    ]),
    said,
    el("p", { class: "muted", text: "These belong to the wall, so they stay when another theme is hung here." }),
  ]);
}

/* The shapes the picker offers, as the bounds each sends: the tallest and the
 * widest, null for no limit. Custom is whatever the two fields hold. */
const SHAPE_CHOICES = [
  ["any", "Any shape", null, null],
  ["portrait", "Portrait and square", null, "1:1"],
  ["landscape", "Landscape and square", "1:1", null],
  ["custom", "Custom", undefined, undefined],
];

/* Which shapes of work this wall shows (#370): the tallest and the widest, as
 * width:height. Set by hand and off by default. The screen's own shape is shown
 * beside them as a hint and never applied. A range that leaves nothing is
 * honoured and the wall goes dark, so after Set the panel says the server's own
 * summary, which says that. */
function shapesPanel(wall, send, changed) {
  const pickerId = `shapes-${wall.wall_id}`;
  const tallestId = `tallest-${wall.wall_id}`;
  const widestId = `widest-${wall.wall_id}`;
  const tallest = el("input", { id: tallestId, type: "text", placeholder: "Any", value: wall.tallest ?? "" });
  const widest = el("input", { id: widestId, type: "text", placeholder: "Any", value: wall.widest ?? "" });
  const picker = el("select", { id: pickerId });
  const chosen = () => {
    const [low, high] = [tallest.value.trim() || null, widest.value.trim() || null];
    const preset = SHAPE_CHOICES.find(([, , t, w]) => t !== undefined && t === low && w === high);
    return preset ? preset[0] : "custom";
  };
  for (const [value, words] of SHAPE_CHOICES) picker.append(el("option", { value, text: words }));
  picker.value = chosen();
  picker.addEventListener("change", () => {
    const [, , low, high] = SHAPE_CHOICES.find(([value]) => value === picker.value);
    if (low === undefined) return tallest.focus();
    tallest.value = low ?? "";
    widest.value = high ?? "";
  });
  for (const field of [tallest, widest]) field.addEventListener("input", () => (picker.value = chosen()));
  const now = el("div", {}, [shapeFacts(wall)]);
  // Said here and the dialog left open, as the mat's is; the card catches up
  // when it closes (`editWall`).
  const said = el("p", { class: "wall-said", role: "status" });
  return el("div", { class: "panel" }, [
    el("h3", { text: "Shapes it shows" }),
    now,
    el("div", { class: "row" }, [
      el("div", { class: "field" }, [el("label", { for: pickerId, text: `Shapes on ${wall.name}` }), picker]),
      // The wall's name in each label, as every other field on the card has it:
      // with two walls, a reader moving by form field hears which wall each is.
      el("div", { class: "field" }, [el("label", { for: tallestId, text: `Tallest on ${wall.name}, as width:height` }), tallest]),
      el("div", { class: "field" }, [el("label", { for: widestId, text: `Widest on ${wall.name}, as width:height` }), widest]),
      el("button", {
        class: "action",
        type: "button",
        text: "Set the shapes",
        "aria-label": `Set the shapes on ${wall.name}`,
        onclick: (event) =>
          attempt(
            event.currentTarget,
            `set the shapes on ${wall.name}`,
            () => send({ tallest: tallest.value.trim() || null, widest: widest.value.trim() || null }),
            {
              then: async (answer) => {
                changed();
                tallest.value = answer.tallest ?? "";
                widest.value = answer.widest ?? "";
                picker.value = chosen();
                fill(now, shapeFacts(answer));
                const fresh = await api(`/api/manifest?wall_id=${encodeURIComponent(wall.wall_id)}`);
                said.textContent = `${wall.name} shows ${answer.shapes ?? "every shape"}. ${fresh.summary}`;
              },
            },
          ),
      }),
    ]),
    said,
    el("p", { class: "muted", text: "A work outside these shapes is left off this wall, and listed above with why." }),
  ]);
}

/* What the wall shows now, and the screen's own shape beside it as a hint. */
function shapeFacts(wall) {
  const screen = wall.sizes_judged_against;
  return facts([
    ["Shows", wall.shapes ?? "every shape"],
    ["Its screen", screen ? screen.shape : "has not said its size"],
  ]);
}

/* What the wall plays at now, the default resolved. */
function rotationFacts(manifest) {
  return facts([
    ["Each work stays up", durationWords(manifest.rotation_interval_seconds)],
    ["Order", manifest.shuffle ? "shuffled" : "as curated"],
  ]);
}

function rotationWords(manifest) {
  return `each work for ${durationWords(manifest.rotation_interval_seconds)}, ${manifest.shuffle ? "shuffled" : "as curated"}`;
}

/* Whole minutes in minutes, anything else in seconds, so a value is never rounded into a different one. */
function durationWords(seconds) {
  return seconds % 60 === 0 ? counted(seconds / 60, "minute") : counted(seconds, "second");
}

/* The mat's modes in the curator's words (`feeds-and-players.md` § Mat modes),
 * in the order the picker offers them: the value, the picker's words, and the
 * words the confirmation says. The empty value is no choice at all: the
 * Player draws its own default, as it would for a public channel. */
const MAT_CHOICES = [
  ["", "Player's own choice", "left to its Player"],
  ["proportional", "Mat around the work", "around the work"],
  ["full", "Mat to the edges", "to the edges"],
  ["none", "No mat", "none"],
];

/* How the wall's Player draws the mat. The colour is always the work's own and
 * the width the Player's, so this chooses only how much of the screen the mat
 * fills. */
function matPanel(wall, changed) {
  const pickerId = `mat-${wall.wall_id}`;
  const picker = el("select", { id: pickerId });
  // Said here and the dialog left open; the card catches up when it closes
  // (`editWall`).
  const said = el("p", { class: "wall-said", role: "status" });
  for (const [value, words] of MAT_CHOICES) {
    picker.append(el("option", { value, text: words, selected: (wall.mat_mode || "") === value }));
  }
  return el("div", { class: "panel" }, [
    el("h3", { text: "Mat" }),
    el("div", { class: "row" }, [
      el("div", { class: "field" }, [el("label", { for: pickerId, text: `Mat on ${wall.name}` }), picker]),
      el("button", {
        class: "action",
        type: "button",
        text: "Set the mat",
        "aria-label": `Set the mat on ${wall.name}`,
        onclick: (event) =>
          attempt(
            event.currentTarget,
            `set the mat on ${wall.name}`,
            () =>
              api(`/api/walls/${encodeURIComponent(wall.wall_id)}/mat`, {
                method: "PUT",
                body: JSON.stringify({ mode: picker.value || null }),
              }),
            {
              then: (answer) => {
                changed();
                const [, , words] = MAT_CHOICES.find(([value]) => value === (answer.mat_mode || ""));
                said.textContent = `Mat on ${wall.name}: ${words}.`;
              },
            },
          ),
      }),
    ]),
    said,
    el("p", {
      class: "muted",
      text: "The mat is always the work's own colour.",
    }),
  ]);
}
