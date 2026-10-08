/* Walls — what is hanging right now, on each wall.
 *
 * Second in the sidebar, in the slot Sonarr gives its Calendar: the nearest *arr
 * idea to "what is showing when" (`information-architecture.md` § The *arr
 * layout). It was the home page until the library took that place, as it has in
 * every *arr app.
 *
 * **Each card leads with what the wall's screen is doing** (`labels-and-surfaces.md`
 * § Display state), which the server derives for each wall and `/api/walls`
 * carries as `display_state`. When it is showing art, that is the work on the
 * wall now (`ia-proposal.md` § Walls), large, with its label facts and a link to
 * its page; otherwise the state in plain words, because a screen somebody is
 * watching television on is not a wall with nothing hung. Below it, what the wall draws from and for
 * how long, then the three acts — **Skip**, **Not this one again** and
 * **Change** — and the way to the wall's history. What the theme holds in full
 * is the theme's page; this card is about the one work a person in the room is
 * looking at.
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
 * asked for: after Skip or *Not this one again*, the card watches the wall's
 * display state until it names the next work (`awaitNext`), and replaces only the
 * work it leads with, so the focus stays wherever the curator left it. Any other
 * repaint goes through `refresh()` with no argument: `refresh(true)` moves focus,
 * and a poll that moves focus is the recorded defect this client already shipped
 * once, on the one screen with a decision on it.
 */

import { attempt } from "../core/acting.js";
import { ago, inWords, readable } from "../core/dates.js";
import { api } from "../core/api.js";
import { absentImage, facts, table } from "../core/badges.js";
import { counted } from "../core/counting.js";
import { hangTheme } from "../core/hanging.js";
import { GLYPHS } from "../core/glyphs.js";
import { el, emptyState, fill, guard, render } from "../core/render.js";
import { screenState, STALE_AFTER_SECONDS, wallScreenLine } from "../core/outputs.js";
import { link, refresh } from "../core/router.js";
import { state } from "../core/state.js";

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

  const [beats, shownBy, builds] = await Promise.all([heartbeats(), clientListing(), Promise.all(walls.walls.map(built))]);
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

  const sections = walls.walls.map((wall, index) => wallSection(wall, builds[index], beats, nows[index], themes.themes, shownBy));
  render(generation, heading(), ...sections, walls.walls.some((wall) => !wall.theme) ? takeDownNote() : null);
}

/* The page's heading, at the size every page's `h1` has: Walls is a page
 * among the others, with no larger heading of its own. */
function heading() {
  return el("h1", { text: "Walls" });
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
 * is there to show it — or that no client is assigned.
 *
 * "Shown by" only where the client reports a screen detected on that output, in
 * a report young enough to speak for now (`core/outputs.js` says why); otherwise
 * the assignment, and what the report says or why it cannot. A wall nobody shows
 * is an ordinary state (`clients.md` § The model), and the one where everything
 * else on this screen happens to no screen at all — so it is said, with the way
 * to Settings › Clients, where a wall is assigned. */
function assignmentLine(wall, shownBy) {
  // A display two clients report is shown by neither, whatever `client_id`
  // still names, so the fault is said in place of the assignment.
  if (wall.display && wall.display.fault) {
    return el("p", { class: "note wall-client wall-fault" }, [
      el("span", { text: `${GLYPHS.problem} ${wall.display.fault.description} ` }),
      link({ view: "clients" }, { text: "See Settings › Clients" }),
    ]);
  }
  if (!wall.client_id) {
    return el("p", { class: "muted wall-client" }, [
      el("span", { text: "No client shows this wall. " }),
      link({ view: "clients" }, { text: "Assign it in Settings › Clients" }),
    ]);
  }
  const client = shownBy.byId ? shownBy.byId.get(wall.client_id) : null;
  return el("p", {
    class: "muted wall-client",
    text: client
      ? wallScreenLine(client.name, wall.output, screenState(client.heartbeat, wall.output), client.heartbeat)
      : `Assigned to ${wall.output} of a client whose name and report could not be read${shownBy.failure ? ` — ${shownBy.failure}` : ""}`,
  });
}

/* Which label outputs caption this wall, and on which client each is.
 *
 * Said only when there is one: most walls have no label, and a line saying so
 * on every card would be noise. Labels are mapped in Settings › Clients, beside
 * the client's other surfaces, and this line links there. */
function labelsLine(wall) {
  if (!wall.labels || !wall.labels.length) return null;
  const named = wall.labels.map((label) => `${label.output} on ${label.client_name}`);
  return el("p", { class: "muted wall-labels" }, [
    el("span", { text: `Captioned by ${listed(named)}. ` }),
    link({ view: "clients" }, { text: "Change in Settings › Clients" }),
  ]);
}

/* "a", "a and b", "a, b and c". */
function listed(names) {
  if (names.length < 2) return names.join("");
  return `${names.slice(0, -1).join(", ")} and ${names[names.length - 1]}`;
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
 * still what the wall reported, so the card says that rather than nothing. */
async function nowOn(wall) {
  const shown = wall.display_state || null;
  const workId = shownWork(shown);
  if (!workId) return { shown, workId: null };
  try {
    const dossier = await api(`/api/works/${encodeURIComponent(workId)}`);
    return { shown, workId, work: dossier.work };
  } catch (failure) {
    return { shown, workId, failure: failure.message };
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

function wallSection(wall, build, beats, now, themes, shownBy) {
  const manifest = build.manifest;
  const reason = reasonFor(wall, build, beats);
  // What the card's acts read the current work from. The lead can be replaced
  // after a Skip without repainting the controls, so they read it here rather
  // than from a value captured when they were drawn.
  const card = { wall, now, lead: nowShowing(wall, now), said: el("p", { class: "wall-said", role: "status" }) };
  return el("section", { class: "wall", "data-wall": wall.wall_id }, [
    // `h2` for the wall and `h3` for what is in it, so the nesting survives a
    // second wall: a reader navigating by heading gets each room with its own
    // work inside it.
    el("h2", { class: "wall-title", text: wall.name }),
    card.lead,
    sourceLine(wall),
    assignmentLine(wall, shownBy),
    labelsLine(wall),
    // The server's own sentence about how much of the theme reached the wall,
    // and not repeated when a reason below is about to say the same thing in
    // more useful words: a screen states a fact once, and two copies of one fact
    // invite the reader to look for the difference between them.
    manifest && reason !== "empty-theme" ? el("p", { class: "note", text: manifest.summary }) : null,
    ...emptiness(reason, wall, build, beats),
    controls(card, themes, reason, manifest),
    card.said,
    manifest ? setup(wall, manifest) : null,
  ]);
}

/* A screen not showing art, in the product's voice. `showing_art` and `silent`
 * are worded where the card is built, because they lead with a work or with
 * when the wall was last heard from. */
const STATE_WORDS = {
  in_use: "Somebody is using the screen",
  dark: "Its screen is off",
  no_screen: "No screen",
  unassigned: "Not assigned to a screen",
  unreachable: "Not known",
};

/* What a state says about the screen, for one the card names in words. A state
 * this client has no words for is said to be not known, never read as another. */
function stateWords(state) {
  return STATE_WORDS[state] || STATE_WORDS.unreachable;
}

/* The lead for a wall that names no work: the state, and since when. */
function stateLead(wall, shown, said, silent) {
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
  return el("div", { class: "wall-now", "data-state": shown.state }, lines);
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
  if (!shown || (shown.state === "silent" && !shown.last)) return el("div", { class: "wall-now", hidden: true });
  const silent = shown.state === "silent";
  const said = silent ? shown.last : shown;
  if (!now.workId) return stateLead(wall, shown, said, silent);
  const when = silent ? `${lastHeard(shown)}, so this may have changed since` : "On the wall now";
  if (now.failure) {
    return el("div", { class: "wall-now" }, [
      el("p", { class: "wall-now-when", text: when }),
      el("p", { class: "note", text: `${wall.name} reports showing a work that could not be read — ${now.failure}.` }),
    ]);
  }
  const work = now.work;
  const artist = work.artist ? work.artist.name : null;
  const image = el("img", {
    // The large size: this box is drawn up to 48rem wide, and the tile's 480 px
    // is soft there on a 2x screen. Still the bare work, never the wall render.
    src: `/api/works/${encodeURIComponent(work.artwork_id)}/thumbnail?size=large`,
    alt: artist ? `${work.title}, ${artist}` : work.title,
  });
  // A file can go away between the heartbeat and this fetch. Without this the
  // lead renders as a blank box — silent, which is the failure mode this whole
  // product exists to refuse.
  image.addEventListener("error", () => {
    image.replaceWith(absentImage("Its image could not be loaded just now."));
  });
  return el("figure", { class: "wall-now" }, [
    el("p", { class: "wall-now-when", text: when }),
    el("div", { class: "wall-now-picture" }, [image]),
    el("figcaption", { class: "wall-now-label" }, [
      el("h3", { class: "wall-now-title" }, [link({ view: "work", id: work.artwork_id }, { text: work.title })]),
      el("p", { class: "wall-now-artist", text: artist || "Artist unrecorded" }),
      work.date_created || work.medium
        ? el("p", { class: "muted wall-now-facts", text: [work.date_created, work.medium].filter(Boolean).join(" · ") })
        : null,
    ]),
  ]);
}

/* What the wall draws from, and for how long: a theme by its name and a link to
 * it, or "a selection" for works hung by choosing them, whose theme is a made-up
 * name the curator never gave (`api-contract.md` § History, selections and
 * *Not this one again*). Every hang lasts until something else is hung, which is
 * said, because the wave-4 schedule will make it a choice. */
function sourceLine(wall) {
  if (!wall.theme) return null;
  if (wall.theme.hidden) {
    return el("p", { class: "wall-source", text: "Drawing from a selection, until changed." });
  }
  return el("p", { class: "wall-source" }, [
    "Drawing from ",
    link({ view: "theme", id: wall.theme.theme_id }, { text: wall.theme.name }),
    ", until changed.",
  ]);
}

/* The four reasons, dispatched. Each is its own function below, and that is not
 * decoration: they are four branches with four texts and four fixes, and a
 * dispatch that fell through to a shared sentence would be the single "nothing is
 * showing" this screen exists not to say. */
function emptiness(reason, wall, build, beats) {
  if (reason === "no-theme") return noThemeHung(wall);
  if (reason === "empty-theme") return emptyTheme(wall, build.manifest);
  if (reason === "silent") return planeSilent(wall, beats.byWall.get(wall.wall_id));
  if (reason === "unreachable") return unreachable(cannotReach(wall, build, beats));
  return [];
}

/* Reason one: no theme has been hung here.
 *
 * The fix is Change in this wall's own section, a few lines below — opened
 * already when nothing is hung — so the sentence points at it rather than
 * sending the curator to another screen for the one act this screen is named for. */
function noThemeHung(wall) {
  return [
    el("p", {
      class: "muted",
      text: `Nothing is hanging on ${wall.name}. Choose a theme below and hang it there.`,
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

/* Skip, Not this one again, Change, and the wall's history: the card's acts.
 *
 * **No take-down control here, deliberately.** Taking down lives on the theme,
 * where it exists to make a theme deletable. It would also read wrong here: a
 * take-down rewrites no manifest, so pressing it on the screen whose whole job is
 * to say what is on the wall would leave the section reading "nothing is hanging"
 * while the television went on showing the pictures. Change is the act on this
 * screen that actually changes the wall. */
function controls(card, themes, reason, manifest) {
  const { wall } = card;
  // Only where something is actually up. Skipping a wall that is showing
  // nothing writes a directive nobody can act on, and offering it would say
  // this screen thinks there is something to move on from.
  //
  // **Both halves are load-bearing.** The reason answers whether a display has
  // spoken for this wall; the manifest answers whether there is anything for a
  // step to advance through. A theme whose works were *all* excluded is not one
  // of the four reasons — `considered` counts entries plus exclusions, so it
  // reads as hanging — and it published an empty rotation.
  const live = reason === "hanging" && manifest.entries.length > 0;
  return el("div", { class: "wall-controls" }, [
    el("div", { class: "row" }, [
      live ? skipButton(card) : null,
      // Only with a work to name: the display state's, which is the one a person in
      // the room is tired of. A wall that has not said what it shows has
      // nothing for this to be about.
      card.now && card.now.workId && wall.theme ? notAgain(card) : null,
      wall.theme ? link({ view: "history", params: { wall: wall.wall_id } }, { class: "action quiet", text: "History", "aria-label": `History of ${wall.name}` }) : null,
    ]),
    change(wall, themes),
  ]);
}

/* Skip: the next work in this wall's rotation, and only this wall's.
 *
 * **Unconfirmed, and that is a decision rather than an oversight.** Flow 6 names
 * activation as the one act that gets a confirmation, and it is the one that
 * replaces everything on a wall. A skip advances by one work in a rotation that
 * was going to advance by itself anyway. A dialog in front of it would teach the
 * curator to dismiss dialogs.
 *
 * The wall changes when its Player next reads the directive, and the card can
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
        () => api("/api/directives", { method: "POST", body: JSON.stringify({ wall_id: wall.wall_id }) }),
        { then: () => awaitNext(card, `Skipped. ${wall.name} shows its next work when its display next reports, usually within a minute.`) },
      ),
  });
}

/* *Not this one again*, and the one question it asks: from this theme, or from
 * every wall. Two different changes (S8 says "nothing else changed"), so the
 * curator says which; neither is Archive, which would take the work out of the
 * library. The choice opens beside the button rather than in a dialog, because
 * the question is the act: there is nothing to confirm once it is answered. */
function notAgain(card) {
  const { wall } = card;
  const choiceId = `not-again-${wall.wall_id}`;
  const choice = el("div", { class: "not-again-choice", id: choiceId, hidden: true });
  const opener = el("button", {
    class: "action quiet",
    type: "button",
    text: "Not this one again",
    "aria-expanded": "false",
    "aria-controls": choiceId,
    "aria-label": `Not this one again on ${wall.name}`,
    onclick: () => {
      const open = choice.hidden;
      choice.hidden = !open;
      opener.setAttribute("aria-expanded", String(open));
      if (open) fillChoice(card, choice, opener);
    },
  });
  return el("span", { class: "not-again" }, [opener, choice]);
}

/* The two answers, built when the question is opened so they name the work the
 * card leads with then, which a Skip may have changed since the card was drawn. */
function fillChoice(card, choice, opener) {
  const { wall } = card;
  const title = card.now.work ? card.now.work.title : "this work";
  const from = wall.theme.hidden ? "this selection" : wall.theme.name;
  const answer = (scope, text, label, act) =>
    el("button", {
      class: "action quiet",
      type: "button",
      text,
      "aria-label": label,
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
              choice.hidden = true;
              opener.setAttribute("aria-expanded", "false");
              return awaitNext(card, notAgainSaid(wall, title, scope, from), scope === "every_wall" ? card.now.workId : null);
            },
          },
        ),
    });
  fill(
    choice,
    el("p", { text: `Not ${title} again — from where?` }),
    answer("theme", `From ${from}`, `Not ${title} again, from ${from}`, `take ${title} out of ${from}`),
    answer("every_wall", "From every wall", `Not ${title} again, from every wall`, `keep ${title} off every wall`),
  );
}

function notAgainSaid(wall, title, scope, from) {
  const done =
    scope === "every_wall"
      ? `${title} is kept off every wall. It stays in the library and in its themes.`
      : `${title} is out of ${from}. Nothing else changed.`;
  return `${done} ${wall.name} shows its next work when its display next reports.`;
}

/* Change: hang a theme on this wall instead. Open already when nothing is
 * hung, because reason one points at it.
 *
 * **A picker rather than a button per theme**, the opposite of the choice
 * `screens/theme.js` makes for walls, and for the reason stated there: a button
 * per target suits a small set, and the themes are the side that grows. It
 * carries the wall's name on its label as well as on the button, so a curator
 * tabbing into the control knows which room it belongs to without reading
 * upward. Selections are not offered: the server leaves them out of the list. */
function change(wall, themes) {
  if (!themes.length) {
    return el("div", { class: "row wall-change" }, [
      el("p", { class: "muted", text: "No theme has been created yet, so there is nothing to hang here." }),
      link({ view: "theme" }, { class: "action", text: "Create a theme" }),
    ]);
  }

  const pickerId = `hang-${wall.wall_id}`;
  const picker = el("select", { id: pickerId });
  for (const placement of themes) {
    picker.append(el("option", { value: placement.theme.theme_id, text: placement.theme.name }));
  }

  return el("details", { class: "wall-change", open: !wall.theme }, [
    el("summary", { class: "action quiet", text: "Change", "aria-label": `Change what ${wall.name} draws from` }),
    el("div", { class: "row" }, [
      el("div", { class: "field" }, [el("label", { for: pickerId, text: `Theme for ${wall.name}` }), picker]),
      el("button", {
        class: "action",
        type: "button",
        text: `Hang on ${wall.name}`,
        onclick: (event) => hang(event.currentTarget, wall, themes, picker.value),
      }),
    ]),
  ]);
}

/* Repaints in place, because the result of this act is on this screen — and it
 * repaints from the published manifest rather than from optimism: `refresh`
 * re-reads everything, so nothing here assumes the activation put up what the
 * preview said it would.
 *
 * The question, the preview and the request are `core/hanging.js`'s — the Theme
 * screen asks the same one, and one act must not have two wordings. */
function hang(control, wall, themes, themeId) {
  const chosen = themes.find((placement) => placement.theme.theme_id === themeId);
  return hangTheme({ control, themeId, themeName: chosen.theme.name, wall, then: refresh });
}

/* After a Skip or *Not this one again*: say what happens next, then watch this
 * wall's display state until it names a different work, and lead the card with it.
 *
 * `gone` is a work that must not be taken for the new one even if the wall
 * names it again (a report written before the Player read the change).
 *
 * Bounded twice: by `STALE_AFTER_SECONDS`, past which a heartbeat that has not
 * moved is a display that has stopped, and by leaving the screen (`state.poll`
 * moves on every navigation, as the run view's chain reads it). Only the lead is
 * replaced, so focus stays where the curator left it. A walls read that fails
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
};

/* How the wall is set up: what of its theme is not reaching it, and how it
 * rotates. Behind a disclosure, because the card is about the work on the wall;
 * this is what to open when the wall is not doing what was expected. */
function setup(wall, manifest) {
  return el("details", { class: "wall-setup" }, [
    el("summary", { text: `How ${wall.name} is set up` }),
    el("div", { class: "panel" }, [
      // Never omitted when empty: a section that appeared only on trouble would
      // train a reader to take its absence as "everything is fine".
      el("h3", { text: `Not showing (${manifest.exclusions.length})` }),
      manifest.exclusions.length
        ? table(
            "Every work this wall draws from that is not on it, and exactly why.",
            ["Title", "Reason", "What is missing"],
            manifest.exclusions.map((x) => [x.title, EXCLUSION_WORDS[x.reason] || x.reason, x.detail]),
          )
        : el("p", {
            class: "muted",
            text: `Every work it draws from reaches the wall: ${counted(manifest.entries.length, "work")} in rotation.`,
          }),
    ]),
    el("div", { class: "panel" }, [
      el("h3", { text: "How it rotates" }),
      facts([
        ["Interval", `${manifest.rotation_interval_seconds} seconds`],
        ["Order", manifest.shuffle ? "shuffled" : "as curated"],
      ]),
    ]),
  ]);
}
